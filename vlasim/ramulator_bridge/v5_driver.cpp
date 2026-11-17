#include <algorithm>
#include <cstdint>
#include <dlfcn.h>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

struct V5Result {
  uint64_t accepted, completed, cycles, rejected, counts[2];
  double first_offer[2], first_done[2], last_done[2];
};
static thread_local std::string error;
extern "C" const char* v5_error() { return error.c_str(); }

extern "C" int v5_execute(const char* library, void** handles, int nh, int channels,
    int width, int limit, uint64_t max_cycles, double tck, uint64_t n,
    const double* issue, const uint8_t* core, const uint64_t* address,
    const uint8_t* write, const uint32_t* epoch, V5Result* result) {
  try {
    if (n == 0 || channels < 1 || width < 1 || limit < 1 || (nh != 1 && nh != channels))
      throw std::runtime_error("invalid replay dimensions");
    void* lib = dlopen(library, RTLD_NOW | RTLD_LOCAL);
    if (!lib) throw std::runtime_error(dlerror());
    auto send = reinterpret_cast<int(*)(void*,uint64_t,int,int64_t,int)>(dlsym(lib,"nr_send"));
    auto tick = reinterpret_cast<int(*)(void*,uint64_t)>(dlsym(lib,"nr_tick"));
    auto pop = reinterpret_cast<int(*)(void*,uint64_t*,uint64_t*)>(dlsym(lib,"nr_pop"));
    auto native_error = reinterpret_cast<const char*(*)()>(dlsym(lib,"nr_error"));
    if (!send || !tick || !pop || !native_error) throw std::runtime_error("missing pinned ABI");
    *result = {};
    for (int c = 0; c < 2; ++c) result->first_offer[c] = result->first_done[c] = result->last_done[c] = -1;
    std::vector<std::vector<uint64_t>> queues(channels);
    for (uint64_t i = 0; i < n; ++i) {
      if (core[i] > 1 || address[i] % 32 || issue[i] < 0 || (i && (issue[i] < issue[i-1] || epoch[i] < epoch[i-1])))
        throw std::runtime_error("invalid transaction array");
      queues[(address[i]/32) % channels].push_back(i);
      if (result->first_offer[core[i]] < 0) result->first_offer[core[i]] = issue[i];
    }
    struct Pending { int core; uint64_t sent; };
    std::unordered_map<uint64_t,Pending> pending;
    std::vector<size_t> positions(channels, 0);
    std::vector<bool> blocked(channels);
    int cursor = 0;
    uint32_t current_epoch = epoch[0];
    while (result->accepted < n || !pending.empty()) {
      for (int h = 0; h < nh; ++h) {
        uint64_t id, when;
        while (pop(handles[h], &id, &when)) {
          auto it = pending.find(id);
          if (it == pending.end() || when < it->second.sent)
            throw std::runtime_error("unknown/duplicate or early native callback");
          const int c = it->second.core;
          const double ns = when * tck;
          if (result->first_done[c] < 0) result->first_done[c] = ns;
          else result->first_done[c] = std::min(result->first_done[c], ns);
          result->last_done[c] = std::max(result->last_done[c], ns);
          ++result->counts[c]; ++result->completed;
          pending.erase(it);
        }
      }
      if (result->accepted == n && pending.empty()) break;
      if (result->cycles >= max_cycles) throw std::runtime_error("native cycle budget exhausted");
      if (pending.empty()) {
        current_epoch = std::numeric_limits<uint32_t>::max();
        for (int ch = 0; ch < channels; ++ch)
          if (positions[ch] < queues[ch].size())
            current_epoch = std::min(current_epoch, epoch[queues[ch][positions[ch]]]);
      }
      std::fill(blocked.begin(), blocked.end(), false);
      int successes = 0;
      while (successes < width && pending.size() < static_cast<size_t>(limit)) {
        bool progress = false;
        for (int attempt = 0; attempt < channels; ++attempt) {
          const int ch = cursor;
          cursor = (cursor+1)%channels;
          if (blocked[ch] || positions[ch] == queues[ch].size()) continue;
          const uint64_t i = queues[ch][positions[ch]];
          if (epoch[i] != current_epoch) continue;
          if (issue[i] > result->cycles*tck+1e-9) continue;
          const uint64_t addr = nh == 1 ? address[i] : (address[i]/32/channels)*32;
          const int ok = send(handles[nh == 1 ? 0 : ch], result->accepted, write[i], addr, core[i]);
          if (ok < 0) throw std::runtime_error(native_error());
          if (!ok) { ++result->rejected; blocked[ch] = true; continue; }
          pending.emplace(result->accepted, Pending{core[i], result->cycles});
          ++result->accepted; ++positions[ch]; ++successes;
          progress = true; break;
        }
        if (!progress) break;
      }
      for (int h = 0; h < nh; ++h)
        if (tick(handles[h],1) < 0) throw std::runtime_error(native_error());
      ++result->cycles;
    }
    if (result->accepted != result->completed) throw std::runtime_error("callback accounting mismatch");
    dlclose(lib);
    return 0;
  } catch (const std::exception& e) { error = e.what(); return -1; }
}
