# Count word frequencies from English text on this machine -> freq.txt (word count)
import os, re, gzip, collections
cnt, tok = collections.Counter(), re.compile(rb"[a-z]{3,8}")
roots = ["/usr/share/doc", "/usr/share/man/man1", "/usr/share/man/man3", "/usr/share/man/man5", "/usr/share/man/man7", "/usr/share/man/man8", "/usr/share/common-licenses", "/usr/share/info"]
seen = 0
for r in roots:
    for d, _, fs in os.walk(r):
        for f in fs:
            p = os.path.join(d, f)
            try:
                data = gzip.open(p).read() if f.endswith(".gz") else open(p, "rb").read()
            except Exception: continue
            if b"\0" in data[:2000]: continue
            seen += len(data)
            cnt.update(tok.findall(data.lower()))
print("bytes", seen, "distinct", len(cnt))
open("freq.txt", "w").write("\n".join(f"{w.decode()} {c}" for w, c in cnt.most_common()))
