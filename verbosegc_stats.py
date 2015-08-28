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

class GC_Stats:

    def __init__(self):
        self.last_ts = None
        self.first_ts = None
        self.first_date = None
        self.last_date = None
        self.heap_after_max = 0
        self.heap_after_max_per = 0
        self.heap_after_max_ds = ''
        self.pause_time_max = 0
        self.pause_time_max_ds = ''
        self.pause_times = []
        self.heap_before = []
        self.heap_after = []
        self.interval_times = []


class VerboseGCParser:

    def __init__(self, filename, jvm_name):
        self.filename = filename
        self.jvm_name = jvm_name
        self.GC = GC_Stats()
        self.fullGC = GC_Stats()
        self.allGC = GC_Stats()

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
    def parenthetic_contents(self, string):
        """Generate parenthesized contents in string as pairs (level, contents)."""
        stack = []
        for i, c in enumerate(string):
            if c == '[':
                stack.append(i)
            elif c == ']' and stack:
                start = stack.pop()
                yield (len(stack), string[start + 1: i])



    def parse_line(self, line):
        #line: date_stamp: time_stamp:gc_info
        parsed_line = re.findall(r'(\S+):\s+(\S+):\s+(.*)', line)
        if not parsed_line:
            raise Exception('Unknown line format: '+parsed_line)
        date_stamp, time_stamp, gc_info = parsed_line[0]
        time_stamp = float(time_stamp)
        date_stamp = parse(date_stamp).strftime('%d-%b-%Y %H:%M:%S')
        for level, content in self.parenthetic_contents(gc_info):
            if level == 0:
                content_type = content.split('[')[0].strip()
                gc_type = None
                if content_type == 'GC':
                    gc_type = self.GC
                elif content_type == 'Full GC':
                    gc_type = self.fullGC
                if gc_type:
                    heaps = re.findall('\]\s+(\w*)K->(\w*)K\((\w*)K\)', content)[0]
                    heap_before, heap_after, heap_size = map(lambda x: int(x), heaps)
                    for stats_gc_type in [gc_type, self.allGC]:
                        if stats_gc_type.last_ts is not None:
                            interval = time_stamp - stats_gc_type.last_ts
                            stats_gc_type.interval_times.append(interval)
                        else:
                            stats_gc_type.first_ts = time_stamp
                            stats_gc_type.first_date = date_stamp
                        pause_time = float(re.findall(r'(\S*) secs', content)[0])
                        stats_gc_type.pause_times.append(pause_time)

                        stats_gc_type.last_ts = time_stamp
                        stats_gc_type.last_date = date_stamp

                        # Update maxs if needed
                        if heap_after> stats_gc_type.heap_after_max:
                            stats_gc_type.heap_after_max = heap_after
                            stats_gc_type.heap_after_max_per = float(heap_after) / (heap_size) * 100
                            stats_gc_type.heap_after_max_ds = date_stamp
                        if pause_time > stats_gc_type.pause_time_max:
                            stats_gc_type.pause_time_max = pause_time
                            stats_gc_type.pause_time_max_ds = date_stamp
            elif level == 1:
                area_type, collection_info = content.split()
                if area_type == 'PSPermGen:':
                    heaps = re.findall('(\w*)K->(\w*)K\((\w*)K\)', collection_info)[0]
                    heap_before, heap_after, heap_size = map(lambda x: int(x), heaps)
                    self.allGC.permgen_max_per = float(heap_after) / (heap_size) * 100


    def print_summary(self):
        total_interval_period = sum(self.allGC.interval_times)
        report = ""
        report += "*** Analyzed GC activity for %s from %s to %s (%s)\n" % (
            self.jvm_name,
            self.allGC.first_date,
            self.allGC.last_date,
            self.seconds2hours(total_interval_period)
        )
        report += """The max heap used memory (after a full GC) was %dK [%2.2f%%] on %s.\n"""\
            % (self.fullGC.heap_after_max, self.fullGC.heap_after_max_per, self.fullGC.heap_after_max_ds)
        if 'permgen_max_per' in self.allGC.__dict__:
            report += """The max PSPermGen memory usage was %2.2f%%\n"""\
                % (self.allGC.permgen_max_per)

        report += """The max pause time was %2.1fs on %s.\n"""\
            % (self.allGC.pause_time_max, self.allGC.pause_time_max_ds)
        report += """Performed %d full GCs, with a pause time of %.2fs (avg) at %s (avg) intervals.\n""" % (\
            len(self.fullGC.pause_times),
            float(sum(self.fullGC.pause_times))/len(self.fullGC.pause_times),
            self.seconds2hours(float(sum(self.fullGC.interval_times))/len(self.fullGC.interval_times))
            )
        report += """Performed %d minor GCs, with a pause time of %.2fs (avg) at %s (avg) intervals.\n""" % (\
            len(self.GC.pause_times),
            float(sum(self.GC.pause_times))/len(self.GC.pause_times),
            self.seconds2hours(float(sum(self.GC.interval_times))/len(self.GC.interval_times))
            )
        report += "***\n"

        print report

gclog_name = sys.argv[1]
jvm_name = sys.argv[2] if len(sys.argv)>2 else 'JVM_NAME'

parser = VerboseGCParser(gclog_name, jvm_name)
parser.parse()
parser.print_summary()
