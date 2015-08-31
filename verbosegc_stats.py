# -*- coding: utf-8 -*-
"""
Copyright [2015]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import sys
import re
from fileinput import FileInput, hook_compressed
from dateutil.parser import parse
from os.path import dirname
from optparse import OptionParser

class GC_Event:

    def __init__(self, date_stamp, time_stamp, pause_time, interval, heap):
        self.date_stamp = date_stamp
        self.time_stamp = time_stamp
        self.pause_time = pause_time
        self.interval = interval
        self.heap_before, self.heap_after, self.heap_size =  heap
        self.permgen_before = self.permgen_after = self.permgen_size = 0

class VerboseGCParser:

    def __init__(self, filename, jvm_name):
        self.filename = filename
        self.jvm_name = jvm_name
        self.gc_events =  {'GC': [], 'FullGC': []}

    def parse(self):
        for line in FileInput(files=[self.filename], openhook=hook_compressed):
            self.parse_line(line)

    def seconds2hours(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        s = int(s)

        if h > 0:
           return "%02dh %02dm %02ss" % (h, m, s)
        elif m > 0:
           return "%02dm %02ss" % (m, s)
        else:
           return "%02ss" % (s)


    #http://stackoverflow.com/a/4285211/401041
    def bracket_contents(self, string):
        """Generate parenthesized contents in string as pairs (level, contents)."""
        stack = []
        for i, c in enumerate(string):
            if c == '[':
                stack.append(i)
            elif c == ']' and stack:
                start = stack.pop()
                yield (len(stack), string[start + 1: i])

    def bracket_inside(self, string):
        bracket_count = 0
        inside = ''
        for c in string:
            if c == '[':
                bracket_count += 1
            elif c== ']':
                bracket_count -= 1
            elif bracket_count == 0:
                inside += c
        return inside


    def parse_line(self, line):
        COLLECT_REGEX = r'(\w*)K->(\w*)K\((\w*)K\)'
        #line: date_stamp: time_stamp:gc_info
        parsed_line = re.findall(r'(\S+):\s+(\S+):\s+(.*)', line)
        if not parsed_line:
            raise Exception('Unknown line format: '+parsed_line)
        ev = None
        date_stamp, time_stamp, gc_info = parsed_line[0]
        time_stamp = float(time_stamp)
        date_stamp = parse(date_stamp).strftime('%d/%b %H:%M:%S')
        for level, content in sorted(self.bracket_contents(gc_info)):
            if level == 0:
                content_type = content.split('[')[0].strip()
                if content_type == 'GC':
                    gc_event_list =  self.gc_events['GC']
                elif content_type == 'Full GC':
                    gc_event_list =  self.gc_events['FullGC']
                else:
                    gc_event_list = None
                if gc_event_list is not None:
                    inside_content = self.bracket_inside(content)
                    heaps = re.findall(COLLECT_REGEX, inside_content)[0]
                    heap = map(lambda x: int(x), heaps)
                    interval = 0
                    if len(gc_event_list) > 0:
                        interval = time_stamp - gc_event_list[-1].time_stamp
                    pause_time = float(re.findall(r'(\S*) secs', inside_content)[0])
                    ev = GC_Event(date_stamp, time_stamp, pause_time, interval, heap)
                    gc_event_list.append(ev)
            elif ev and level == 1:
                area_type, collection_info = content.split()
                inside_content = self.bracket_inside(content)
                if area_type == 'PSPermGen:':
                    heaps = re.findall(COLLECT_REGEX, inside_content)[0]
                    heaps = map(lambda x: int(x), heaps)
                    ev.permgen_before, ev.permgen_after, ev.permgen_size = heaps


    def print_summary(self):
        gc_events = self.gc_events['GC']
        fullgc_events = self.gc_events['FullGC']
        all_events = gc_events + fullgc_events

        report = ""
        report += "*** Analyzed GC activity for %s from %s to %s (%s)\n" % (
            self.jvm_name,
            all_events[0].date_stamp,
            all_events[-1].date_stamp,
            self.seconds2hours(max([x.time_stamp for x in all_events]) - min([x.time_stamp for x in all_events]))
        )
        max_heap_after = max([x.heap_after for x in fullgc_events])
        max_heap_after_perc = max([float(x.heap_after) / x.heap_size * 100  for x in fullgc_events])
        mas_heap_time_stamp = filter(lambda x: x.heap_after == max_heap_after, fullgc_events)[0].date_stamp
        report += """The max heap used memory (after a full GC) was %dK [%2.2f%%] on %s.\n""" \
            % (max_heap_after, max_heap_after_perc, mas_heap_time_stamp)
        max_permgen_after = max([x.permgen_after for x in all_events])
        max_permgen_after_perc = max([float(x.permgen_after) / x.permgen_size * 100  for x in all_events if x.permgen_size] or [0])
        max_permgen_after_date_stamp = filter(lambda x: x.permgen_after == max_permgen_after, all_events)[0].date_stamp
        report += """The max PSPermGen was %dK [%2.2f%%] on %s.\n""" \
            % (max_permgen_after, max_permgen_after_perc, max_permgen_after_date_stamp)
        max_pause_time = max([x.pause_time for x in all_events])
        max_pause_time_stamp = filter(lambda x: x.pause_time == max_pause_time, all_events)[0].date_stamp
        report += """The max pause time was %2.1fs on %s.\n""" \
            % (max_pause_time, max_pause_time_stamp)

        for key, keystr  in [('FullGC', 'full GCs'), ('GC', 'minor GCs')]:
            gc_events = self.gc_events[key]
            count = len(gc_events)
            pause_avg = sum([x.pause_time for x in gc_events]) / float(count)
            interval_avg = sum([x.interval for x in gc_events]) / float(count-1)
            heap_after_avg = sum([x.heap_after for x in gc_events]) / float(count)
            report += """%d %s, with a pause time of %.2fs (avg) at %s (avg) intervals, resulting in %.0fK (avg) used heap.\n""" \
                % (
                    count, keystr,
                    pause_avg,
                    self.seconds2hours(interval_avg),
                    heap_after_avg,
                )


        print report

def parse_args():
    cmd_parser = OptionParser()

    cmd_parser.add_option("-q", "--quiet", dest="quiet",
        help="No information ouput", action="store_true", default=False)
    cmd_parser.add_option("-r", "--results", dest="results",
        help="Calculate perofrmance results", action="store_true", default=False)
    (options, args) = cmd_parser.parse_args()

    return options, args

def main():
    (options, args) = parse_args()
    gclog_name = args.pop(0)
    jvm_name = args.pop(0) if args else dirname(gclog_name).split('/')[-1]
    parser = VerboseGCParser(gclog_name, jvm_name)
    parser.parse()
    parser.print_summary()



if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print "Interrupted"
