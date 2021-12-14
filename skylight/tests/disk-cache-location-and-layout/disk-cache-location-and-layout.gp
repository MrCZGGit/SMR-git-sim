reset

set terminal postscript eps color enhanced size 5,3.5 font "Times-Roman" 22
set output 'disk-cache-location-and-layout.eps'

set ylabel "Latency (ms)"
set xlabel 'Operation Number'


set yrange[0:39]
set xrange[0:1500]
set ytics 10

set border 3 back
set tics nomirror out scale 0.75

plot "read-low_lat.log" u 0:($2/1000) t 'low offset' w l, \
     "read-mid_lat.log" u 0:($2/1000) t 'mid offset' w l, \
     "read-high_lat.log" u 0:($2/1000) t 'high offset' w l
