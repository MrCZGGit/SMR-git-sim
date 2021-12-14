header = """fio version 2 iolog
%s add
%s open
"""
trailer = """
%s close"""

def gen_trace(trace, device, offsets, size=4096):
    f = open('%s.trace' % (trace,), 'w')
    f.write(
        header % (device, device) + \
        '\n'.join(["%s %s %d %d" % (device, trace, o, size)
                   for o in offsets]) + \
        trailer % (device,))
    f.close()
