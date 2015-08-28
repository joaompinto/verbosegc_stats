# -*- coding: utf-8 -*-
from fileinput import FileInput, hook_compressed
import re

class GC_Stats:
    last_ts = None
    first_gc_ts = None
    pause_times = []
    heap_before = []
    heap_after = []
    interval_times = []


#http://stackoverflow.com/a/4285211/401041
def parenthetic_contents(string):
    """Generate parenthesized contents in string as pairs (level, contents)."""
    stack = []
    for i, c in enumerate(string):
        if c == '[':
            stack.append(i)
        elif c == ']' and stack:
            start = stack.pop()
            yield (len(stack), string[start + 1: i])

def seconds2hours(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    s = int(s)
    return "%02dh %02dm %02ss" % (h, m, s)

def parse_line(line):
    #line: date_stamp: time_stamp:gc_info
    parsed_line = re.findall(r'(\S+):\s+(\S+):\s+(.*)', line)
    if not parsed_line:
        raise Exception('Unknown line format: '+parsed_line)
    date_stamp, time_stamp, gc_info = parsed_line[0]
    time_stamp = float(time_stamp)
    if GC_Stats.first_gc_ts is None:
        GC_Stats.first_gc_ts = time_stamp

    for level, content in parenthetic_contents(gc_info):
        if level == 0:
            content_type = content.split('[')[0].strip()
            if content_type == 'GC':
                pause_time = float(re.findall(r'(\S*) secs', content)[0])
                GC_Stats.pause_times.append(pause_time)

            if 'GC' in content_type and GC_Stats.last_ts:
                GC_Stats.interval_times.append(time_stamp - GC_Stats.last_ts)
    GC_Stats.last_ts = time_stamp


for line in FileInput(openhook=hook_compressed):
    parse_line(line)

total_interval_period = sum(GC_Stats.interval_times)
avg_interval_period = total_interval_period / len(GC_Stats.interval_times)

print "Total run time      :", seconds2hours(total_interval_period)
print "Avg interval period : %.2f" % avg_interval_period
print "Accummulated GC time: %.2f" % sum(GC_Stats.pause_times)
print "Number of GC pauses : %.2f" % len(GC_Stats.pause_times)
print "Avg GC time         : %.2f" % float(sum(GC_Stats.pause_times))/len(GC_Stats.pause_times) if len(GC_Stats.pause_times) > 0 else float('nan')
print "Min/Max GC time     : %.2f/%.2f" % (min(GC_Stats.pause_times), max(GC_Stats.pause_times))
print
