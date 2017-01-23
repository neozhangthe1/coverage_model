#!/usr/bin/python
import os
import sys

run = os.system

def split_seg(line):
    p1 = line.find(">")+1
    p2 = line.rfind("<")
    return [ line[:p1], line[p1:p2], line[p2:] ]

def plain2sgm(trg_plain, src_sgm, trg_sgm):
    "Converse plain format to sgm format"
    fin_trg_plain = file(trg_plain , "r")
    fin_src_sgm = file(src_sgm, "r")
    fout = file(trg_sgm, "w")
    
    #head
    doc_head = fin_src_sgm.readline().rstrip().replace("srcset", "tstset")
    if doc_head.find("trglang") == -1 :
        doc_head = doc_head.replace(">", " trglang=\"English\">")
    print(doc_head, file=fout)

    for line in fin_src_sgm:
        line = line.rstrip()
        #process doc tag
        if "<doc" in line or "<Doc" in line or "<DOC" in line:
            p1 = line.find('"')
            p2 = line.find('"' , p1+1)
            id = line[p1+1 : p2]
            print('''<doc docid="%s" sysid="hiero">''' %id, file=fout)
        elif line.startswith("<seg"):
            head, body , tail  = split_seg(line)
            print(head, fin_trg_plain.readline().rstrip(), tail, file=fout)
        elif line.strip() == "</srcset>":
            print("</tstset>", file=fout)
        else:
            print(line, file=fout)
    


if __name__ == "__main__" :
    if (len(sys.argv) != 4) :
        print("exe trg_plain src_sgm out_sgm", file=sys.stderr)
        sys.exit(0)

    trg_plain = sys.argv[1]
    src_sgm = sys.argv[2]
    trg_sgm = sys.argv[3]

    plain2sgm(trg_plain, src_sgm, trg_sgm)

