include ../parameters.mk

all:
	sudo hdparm -a256 -A1 -W0 $(DEVICE)
	sudo fio read.fio --filename=$(DEVICE)
	gnuplot zone-profile.gp
	evince zone-profile.eps

clean:
	rm -rf *.log *.eps
