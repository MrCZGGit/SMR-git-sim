reset

set terminal postscript eps color enhanced size 5,3.5 font "Times-Roman" 22
set output 'drive-type.eps'

set ylabel 'Latency (ms)'
set xlabel 'Operation Number'

set xrange [0:256]
set yrange [0:320]
set ytics 150

set border 3 back
set tics nomirror out scale 0.75

p "rand-write_lat.log" u 0:($2/1000) notitle w l
