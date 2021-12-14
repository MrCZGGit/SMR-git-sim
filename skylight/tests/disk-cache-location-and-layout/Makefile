include ../parameters.mk

all:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)

	sudo fio write.fio --filename=$(DEVICE) --offset=$(LOW_OFFSET)
	sudo fio read.fio --filename=$(DEVICE) --offset=$(LOW_OFFSET) \
		--write_lat_log=read-low

	sudo fio write.fio --filename=$(DEVICE) --offset=$(MID_OFFSET)
	sudo fio read.fio --filename=$(DEVICE) --offset=$(MID_OFFSET) \
		--write_lat_log=read-mid

	sudo fio write.fio --filename=$(DEVICE) --offset=$(HIGH_OFFSET)
	sudo fio read.fio --filename=$(DEVICE) --offset=$(HIGH_OFFSET) \
		--write_lat_log=read-high

	gnuplot disk-cache-location-and-layout.gp
	evince disk-cache-location-and-layout.eps

clean:
	rm -rf *.log *.eps
