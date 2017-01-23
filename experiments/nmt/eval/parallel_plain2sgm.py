#!/usr/bin/python
import os
import sys

if __name__ == "__main__" :
    if (len(sys.argv) != 5) :
        print("exe in_src_plain in_ref_plain out_src_sgm out_ref_sgm", file=sys.stderr)
        sys.exit(0)

    fin_src_plain = open(sys.argv[1])
    fin_ref_plain = open(sys.argv[2])
    fout_src_sgm = open(sys.argv[3], 'w')
    fout_ref_sgm = open(sys.argv[4], 'w')

    last_src_line = ''
    refs = []

    parallel_list = []

    while 1:
        try:
            src_line = fin_src_plain.next().strip()
            ref_line = fin_ref_plain.next().strip()
        except StopIteration:
            break


        if src_line == last_src_line:
            refs.append(ref_line)
        else:
            if len(refs) > 0:
                parallel_list.append((last_src_line, refs))

            refs = [ref_line]
            last_src_line = src_line

    if len(refs) > 0:
        parallel_list.append((last_src_line, refs))


    # write source sgm file
    print('<srcset setid="funny" srclang="Chinese" trglang="English">\n<doc docid="document">', file=fout_src_sgm)
    for id in range(len(parallel_list)):
        print('<seg id=%d>%s</seg>' % (id, parallel_list[id][0]), file=fout_src_sgm)
    print('</doc>\n</srcset>', file=fout_src_sgm)


    # write reference sgm file
    print('<refset setid="funny-ref" srclang="Chinese" trglang="English">', file=fout_ref_sgm)
    ref_num = len(refs)
    for sysid in range(ref_num):
        print('<doc docid="document" sysid="r%d">'%(sysid), file=fout_ref_sgm)
        for id in range(len(parallel_list)):
            print('<seg id=%d>%s</seg>' % (id, parallel_list[id][1][sysid]), file=fout_ref_sgm)
        print('</doc>', file=fout_ref_sgm)
    print('</refset>', file=fout_ref_sgm)
