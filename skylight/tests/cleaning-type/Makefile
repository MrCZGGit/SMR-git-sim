include ../parameters.mk

all:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)

	sudo fio write.fio --filename=$(DEVICE) --offset=$(MID_OFFSET)
	sleep 3
	sudo fio read.fio --filename=$(DEVICE) --offset=$(MID_OFFSET) \
		--write_lat_log=read-mid

	gnuplot cleaning-type.gp
	evince cleaning-type.eps

clean:
	rm -rf *.log *.eps
