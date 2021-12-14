reset

set terminal postscript eps color enhanced size 5,3.5 font "Times-Roman" 22
set output 'zone-profile.eps'

set xlabel 'Time (s)'
set ylabel 'Throughput (MiB/s)'

set border 3 back
set tics nomirror out scale 0.75

unset key

plot 'seq-read_bw.log' u ($1/1000):($2/1000) w l
