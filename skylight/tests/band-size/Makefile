include ../parameters.mk

all:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	./mktrace.py $(DEVICE) $(MID_OFFSET) $(ESTIMATE) $(ACCURACY)
	sudo fio replay.fio --read_iolog=write.trace
	sleep 3
	sudo fio replay.fio --read_iolog=read.trace
	gnuplot band-size.gp
	evince band-size.eps

clean:
	rm -rf *.log *.eps
