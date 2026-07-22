#!/usr/bin/env python3
"""Genera la certificación estructural reproducible del catálogo ToneFinish."""
import argparse, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from processes import registry, write_catalog_certification

parser=argparse.ArgumentParser()
parser.add_argument("--output",default="docs/audio-plugin-certification.json")
args=parser.parse_args()
path=write_catalog_certification(ROOT/args.output,registry)
print(path)
