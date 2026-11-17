`timescale 1ns/1ps
module v6_rtl_tb;
  reg clk=0;
  always #5 clk=~clk;
  reg [15:0] a,b;
  reg [31:0] acc,va,vb;
  wire [31:0] result,vr;
  v6_pe pe(clk,a,b,acc,result);
  v6_vector_lane vector_lane(va,vb,vr);
  task check_pe;
    input [15:0] av,bv;
    input [31:0] cv,expected;
    begin
      @(negedge clk); a=av; b=bv; acc=cv;
      @(posedge clk); @(posedge clk); #1;
      if(result!==expected) $fatal(1,"PE mismatch %h != %h",result,expected);
    end
  endtask
  initial begin
    a=0;b=0;acc=0;va=32'h3f800000;vb=32'h40000000;
    #1;
    if(vr!==32'h40400000) $fatal(1,"Vector add mismatch");
    check_pe(16'h3f80,16'h4000,32'h40400000,32'h40a00000);
    check_pe(16'hbfc0,16'h4000,32'h3f000000,32'hc0200000);
    check_pe(16'h0000,16'h4040,32'hbf800000,32'hbf800000);
    check_pe(16'h3f00,16'h3f00,32'h3f400000,32'h3f800000);
    check_pe(16'h3f80,16'h3f80,32'hbf800000,32'h00000000);
    $display("PASS: five finite BF16/FP32 PE vectors and one FP32 vector addition");
    $finish;
  end
endmodule
