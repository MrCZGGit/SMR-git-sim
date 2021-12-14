include ../parameters.mk

all:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	./mktrace.py $(DEVICE)
	sudo fio write.fio
	gnuplot drive-type.gp
	evince drive-type.eps

clean:
	rm -rf *.eps *.log
