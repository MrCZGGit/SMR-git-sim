include ../parameters.mk

all:
	sudo hdparm -a0 -A0 -W0 $(DEVICE)
	./mktrace.py $(DEVICE) $(BAND_A_OFFSET) $(BAND_B_OFFSET) $(TRACK_SIZE) \
		$(BLOCK_SIZE)
	sudo fio replay.fio --write_lat_log=before
	sudo fio write.fio --filename=$(DEVICE) --offset=$(BAND_B_OFFSET) --size=$(TRACK_SIZE)
	sleep 2
	sudo fio replay.fio --write_lat_log=after
	gnuplot mapping-type.gp
	evince mapping-type.eps

clean:
	rm -rf *.log *.eps
