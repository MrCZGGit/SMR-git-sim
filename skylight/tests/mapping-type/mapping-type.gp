reset

set terminal postscript eps color enhanced size 5,3.5 font "Times-Roman" 22
set output 'mapping-type.eps'

set ylabel "Latency (ms)"
set xlabel 'Operation Number'

set border 3 back
set tics nomirror out scale 0.75

set multiplot layout 2,1

plot "before_lat.log" u 0:($2/1000) t 'before' w l
plot "after_lat.log" u 0:($2/1000) t 'after' w l
