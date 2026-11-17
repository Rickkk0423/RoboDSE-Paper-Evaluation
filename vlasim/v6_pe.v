// Area-only HardFloat wrapper: bf16 inputs, fp32 fused accumulation and PE registers.
module v6_pe(input clk, input [15:0] a, b, input [31:0] acc, output reg [31:0] result);
  reg [15:0] ar, br;
  reg [31:0] cr;
  wire [32:0] ra, rb, rc, ro;
  wire [31:0] next_result;
  wire [4:0] flags;
  always @(posedge clk) begin ar <= a; br <= b; cr <= acc; result <= next_result; end
  fNToRecFN #(8,24) cvta({ar,16'b0},ra);
  fNToRecFN #(8,24) cvtb({br,16'b0},rb);
  fNToRecFN #(8,24) cvtc(cr,rc);
  mulAddRecFN #(8,24) mac(1'b0,2'b00,ra,rb,rc,3'b000,ro,flags);
  recFNToFN #(8,24) cvto(ro,next_result);
endmodule

module v6_vector_lane(input [31:0] a,b, output [31:0] result);
  wire [32:0] ra,rb,ro;
  wire [4:0] flags;
  fNToRecFN #(8,24) cvta(a,ra);
  fNToRecFN #(8,24) cvtb(b,rb);
  addRecFN #(8,24) add(1'b0,1'b0,ra,rb,3'b000,ro,flags);
  recFNToFN #(8,24) cvto(ro,result);
endmodule
