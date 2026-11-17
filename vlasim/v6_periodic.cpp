// V6 sensitivity fork: independent stream bandwidth multipliers, not a refitted model.
// Original event scheduling and traffic accounting retained from the frozen V5.1 kernel.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <string>
#include <utility>
#include <vector>

struct Op { double compute, bytes, weight, kv; int attention; };
struct Group { const Op* ops=nullptr; int length=0, index=0; double rem=0, busy=0, bytes=0, kv=0; };
static thread_local std::string error;
extern "C" const char* periodic_error() { return error.c_str(); }

extern "C" int periodic_run(int n, int warmup, int k, int serial, double period,
    double peak, double eta_seq, double eta_mix, double vlm_scale, double dit_scale,
    int priority, double partition,
    const Op* vlm, int nv, const Op* dit, const int* offsets, const int* lengths,
    double* requests, double* rounds, double* summary) {
  if (n-warmup-k-2<2 || k<1 || k>3 || period<=0 || nv<1) {
    error="invalid periodic kernel dimensions"; return -1;
  }
  const double inf=std::numeric_limits<double>::infinity();
  Group g[2];
  std::deque<int> pending, ready;
  std::vector<int> slots(k,-1), rr;
  std::vector<std::pair<double,int>> qe{{0.,0}};
  std::vector<std::array<double,6>> totals(n);
  int next_obs=0, next_id=0, vreq=-1, completed=0, nr=0, mask=0;
  double t=0, round_start=0, previous_round_end=0;
  std::array<double,10> rd{};
  std::fill(requests,requests+n*4,0.);
  auto active=[&](int i) { return g[i].index<g[i].length; };
  auto load=[&](int i, const Op* ops, int count) { g[i].ops=ops;g[i].index=0;g[i].length=count;g[i].rem=1.; };
  while (completed<n) {
    while (next_obs<n && next_obs*period<=t) {
      requests[next_obs*4]=next_obs*period;pending.push_back(next_obs++);
      qe.emplace_back(t,pending.size());
    }
    bool progressed=true;
    while (progressed) {
      progressed=false;
      if (!active(0) && vreq<0 && next_id<n) {
        bool can=!pending.empty();
        if (serial) can=can && ready.empty() && rr.empty() &&
          std::all_of(slots.begin(),slots.end(),[](int r){return r<0;});
        if (can && (!serial || !active(1))) {
          vreq=pending.front();pending.pop_front();++next_id;
          requests[vreq*4+1]=t;qe.emplace_back(t,pending.size());
          load(0,vlm,nv);progressed=true;
        }
      }
      if (!active(1) && rr.empty()) {
        bool occupied=false;
        for (int s=1;s<k;++s) occupied=occupied || slots[s]>=0;
        bool start=false;
        if (!ready.empty()) { slots[0]=ready.front();ready.pop_front();start=true; }
        else if (occupied && vreq<0 && next_id>=n) start=true;
        if (start) {
          rr=slots;mask=0;
          for (int s=0;s<k;++s) if (rr[s]>=0) mask|=1<<s;
          round_start=t;rd={};rd[9]=t-previous_round_end;
          load(1,dit+offsets[mask],lengths[mask]);progressed=true;
        }
      }
    }
    double tc[2]={0.,0.}, dem[2]={0.,0.}, alloc[2]={0.,0.}, rate[2]={0.,0.};
    for (int i=0;i<2;++i) if (active(i)) {
      const Op& o=g[i].ops[g[i].index];tc[i]=o.compute;
      dem[i]=o.bytes<=0 ? 0. : (tc[i]>0 ? o.bytes/tc[i] : peak);
    }
    if (partition>0 && !serial) {
      alloc[0]=std::min(dem[0],peak*eta_seq*partition);
      alloc[1]=std::min(dem[1],peak*eta_seq*(1-partition));
    } else {
      int live=(dem[0]>0)+(dem[1]>0);
      double bw=std::min(peak,peak*eta_seq*(live>=2 ? eta_mix : 1.));
      if (priority && live>=2) {
        alloc[0]=std::min(dem[0],bw);alloc[1]=std::min(dem[1],bw-alloc[0]);
      } else if (live==1) {
        for (int i=0;i<2;++i) alloc[i]=std::min(dem[i],bw);
      } else if (live==2) {
        // Same water-filling and summation order as DRAMModel._allocate_static.
        double rem=bw;bool hungry[2]={true,true};int left=2;
        while (rem>1e-9 && left) {
          double share=rem/left;bool sat[2]={hungry[0]&&dem[0]<=share,hungry[1]&&dem[1]<=share};
          if (!sat[0]&&!sat[1]) {for(int i=0;i<2;++i) if(hungry[i]) alloc[i]=share;break;}
          for(int i=0;i<2;++i) if(sat[i]) {alloc[i]=dem[i];rem-=dem[i];hungry[i]=false;--left;}
        }
      }
    }
    alloc[0]*=vlm_scale;alloc[1]*=dit_scale;
    double allocated=alloc[0]+alloc[1];
    if (allocated>peak) {alloc[0]*=peak/allocated;alloc[1]*=peak/allocated;}
    double dt=inf;
    for(int i=0;i<2;++i) if(active(i)) {
      const Op& o=g[i].ops[g[i].index];
      rate[i]=std::min(tc[i]>0 ? 1/tc[i] : inf,o.bytes>0 ? alloc[i]/o.bytes : inf);
      if(!std::isfinite(rate[i])) rate[i]=1e12;
      if(rate[i]>0) dt=std::min(dt,g[i].rem/rate[i]);
    }
    if(next_obs<n) dt=std::min(dt,std::max(0.,next_obs*period-t));
    if(!std::isfinite(dt)) {error="deadlock in periodic kernel";return -1;}
    for(int i=0;i<2;++i) if(active(i)) {
      const Op& o=g[i].ops[g[i].index];
      double frac=std::min(g[i].rem,rate[i]*dt);
      g[i].rem-=frac;g[i].busy+=dt;g[i].bytes+=frac*o.bytes;g[i].kv+=frac*o.kv;
      if(i==1) {
        rd[3]+=frac*tc[i];rd[4]+=std::max(0.,dt-frac*tc[i]);
        rd[o.attention?6:5]+=dt;rd[7]+=frac*o.bytes;rd[8]+=frac*o.weight;
      }
    }
    t+=dt;
    if(active(0) && g[0].rem<=1e-12) {
      ++g[0].index;g[0].rem=1.;
      if(!active(0)) {requests[vreq*4+2]=t;ready.push_back(vreq);vreq=-1;}
    }
    if(active(1) && g[1].rem<=1e-12) {
      ++g[1].index;g[1].rem=1.;
      if(!active(1)) {
        rd[0]=round_start;rd[1]=t;rd[2]=t-round_start;
        for(int j=0;j<10;++j) rounds[nr*12+j]=rd[j];
        rounds[nr*12+10]=mask;rounds[nr*12+11]=rr[0]<0;++nr;previous_round_end=t;
        int last=rr[k-1];
        if(last>=0) {
          requests[last*4+3]=t;++completed;
          totals[last]={g[0].busy,g[1].busy,g[0].bytes,g[1].bytes,g[0].kv,g[1].kv};
        }
        slots[0]=-1;for(int s=1;s<k;++s) slots[s]=rr[s-1];rr.clear();
      }
    }
  }
  double lo=requests[warmup*4+3],hi=requests[(n-k-3)*4+3];
  int qmax=0;
  for(size_t i=0;i<qe.size();++i) {
    double a=qe[i].first,b=i+1<qe.size()?qe[i+1].first:t;
    if ((a>=lo && a<=hi) || std::min(b,hi)>std::max(a,lo)) qmax=std::max(qmax,qe[i].second);
  }
  summary[0]=t;summary[1]=g[0].busy/t;summary[2]=g[1].busy/t;
  summary[3]=g[0].bytes/n/1e9;summary[4]=g[1].bytes/n/1e9;
  summary[5]=qmax;summary[6]=nr;
  for(int i=0;i<6;++i) summary[7+i]=(totals[n-k-3][i]-totals[warmup][i])/(hi-lo);
  return 0;
}
