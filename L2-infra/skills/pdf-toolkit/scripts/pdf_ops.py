#!/usr/bin/env python3
"""PDF page-level toolkit: merge / split / rotate / extract.

Usage:
  pdf_ops.py merge  <in1.pdf> <in2.pdf> [...] -o out.pdf
  pdf_ops.py split  <in.pdf> -o <outdir> [--prefix name]
  pdf_ops.py rotate <in.pdf> -o out.pdf --angle 90|180|270 [--pages 1,3-5]
  pdf_ops.py extract <in.pdf> -o out.pdf --pages 1,3-5

Pages are 1-based. Ranges like 1-5, single pages 3, negatives not allowed.
Exit 0 on success; non-zero with a one-line reason on stderr.
"""
import argparse
import os
import sys

from pypdf import PdfReader, PdfWriter


def parse_pages(spec: str, total: int) -> list[int]:
    """Parse '1,3-5' into 0-based page indices, validating bounds."""
    picked = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a, b = int(a), int(b)
            if not (1 <= a <= b <= total):
                raise ValueError(f"range {a}-{b} out of bounds (1-{total})")
            picked.extend(range(a - 1, b))
        else:
            p = int(part)
            if not (1 <= p <= total):
                raise ValueError(f"page {p} out of bounds (1-{total})")
            picked.append(p - 1)
    if not picked:
        raise ValueError("no pages selected")
    return picked


def cmd_merge(args):
    w = PdfWriter()
    for f in args.inputs:
        r = PdfReader(f)
        if r.is_encrypted:
            try:
                r.decrypt("")
            except Exception:
                return f"error: {f} is encrypted (password-protected)"
        w.append(r)
    with open(args.output, "wb") as fh:
        w.write(fh)
    total = len(PdfReader(args.output).pages)
    print(f"merged {len(args.inputs)} files -> {args.output} ({total} pages)")
    return 0


def cmd_split(args):
    os.makedirs(args.output, exist_ok=True)
    prefix = args.prefix or os.path.splitext(os.path.basename(args.input))[0]
    r = PdfReader(args.input)
    if r.is_encrypted:
        return f"error: {args.input} is encrypted"
    n = len(r.pages)
    for i in range(n):
        w = PdfWriter()
        w.add_page(r.pages[i])
        out = os.path.join(args.output, f"{prefix}_{i+1:03d}.pdf")
        with open(out, "wb") as fh:
            w.write(fh)
    print(f"split {args.input} -> {n} files in {args.output} (prefix: {prefix}_NNN.pdf)")
    return 0


def cmd_rotate(args):
    r = PdfReader(args.input)
    if r.is_encrypted:
        return f"error: {args.input} is encrypted"
    w = PdfWriter()
    pages = parse_pages(args.pages, len(r.pages)) if args.pages else list(range(len(r.pages)))
    for i, page in enumerate(r.pages):
        if i in pages:
            page.rotate(args.angle)
        w.add_page(page)
    with open(args.output, "wb") as fh:
        w.write(fh)
    print(f"rotated {len(pages)}/{len(r.pages)} pages by {args.angle}° -> {args.output}")
    return 0


def cmd_extract(args):
    r = PdfReader(args.input)
    if r.is_encrypted:
        return f"error: {args.input} is encrypted"
    picked = parse_pages(args.pages, len(r.pages))
    w = PdfWriter()
    for i in picked:
        w.add_page(r.pages[i])
    with open(args.output, "wb") as fh:
        w.write(fh)
    print(f"extracted {len(picked)} pages -> {args.output}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", help="merge PDFs in given order")
    m.add_argument("inputs", nargs="+", help="input PDFs, order matters")
    m.add_argument("-o", "--output", required=True)
    m.set_defaults(func=cmd_merge)

    s = sub.add_parser("split", help="split each page to its own PDF")
    s.add_argument("input")
    s.add_argument("-o", "--output", required=True, help="output directory")
    s.add_argument("--prefix", default=None)
    s.set_defaults(func=cmd_split)

    r_ = sub.add_parser("rotate", help="rotate pages by 90/180/270")
    r_.add_argument("input")
    r_.add_argument("-o", "--output", required=True)
    r_.add_argument("--angle", type=int, required=True, choices=[90, 180, 270])
    r_.add_argument("--pages", default=None, help="e.g. 1,3-5; default all")
    r_.set_defaults(func=cmd_rotate)

    e = sub.add_parser("extract", help="extract selected pages to a new PDF")
    e.add_argument("input")
    e.add_argument("-o", "--output", required=True)
    e.add_argument("--pages", required=True, help="e.g. 1,3-5")
    e.set_defaults(func=cmd_extract)

    args = p.parse_args()
    try:
        rc = args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if isinstance(rc, str):
        print(rc, file=sys.stderr)
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
