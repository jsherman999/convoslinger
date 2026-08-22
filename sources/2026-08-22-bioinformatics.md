That reframes it usefully — a Costa Rica field course with insects, plants, and bats almost certainly means **DNA barcoding**, not genome assembly. That's good news: it's the most tractable corner of bioinformatics, and Biopython is unusually well-matched to it.

The workflow is short enough for a teen to hold in their head: sequence a standard marker region, compare it to a reference database, see whether the molecular ID matches the morphological one. For animals that marker is mitochondrial COI, matched against the Barcode of Life Data System, which assigns specimens Barcode Index Numbers algorithmically. Plants use rbcL, matK, or ITS2 instead — worth knowing, since the class will likely handle both.

**Miniforge sources:**
- The [conda-forge/miniforge README](https://github.com/conda-forge/miniforge) is the canonical one. Signed, notarized PKG installers are available for macOS as of 2026 — and the project explicitly recommends against installing Miniforge via Homebrew, since the repackaging causes untested incompatibilities. Grab the Apple Silicon PKG.
- For someone new to the concept, the BiA-PoL "[Getting Started with Miniforge and Python](https://biapol.github.io/blog/mara_lampert/getting_started_with_miniforge_and_python/readme.html)" post is the friendliest walkthrough. Its one rule worth tattooing on the teen: never install into the base environment.

**Biopython sources:**
- The [Tutorial & Cookbook](https://biopython.org/docs/latest/Tutorial/) is the real documentation, not a supplement. The current release is 1.87, from March 2026. One trap: older guides link to the old `biopython.org/DIST/docs/tutorial/` PDF, which is superseded — use the `/docs/latest/` path.
- Chris Rands' Biopython Notebook tutorial (linked from biopython.org's docs page) is Jupyter-native, which fits your setup.

A starting environment:

```bash
conda create -n barcode -c conda-forge -c bioconda \
  python=3.12 biopython jupyterlab pandas matplotlib \
  mafft seqkit iqtree
```

If any of those lack an arm64 build, that's your OrbStack fallback — pull the biocontainer rather than fighting it.

The detail that'll sell it: `Bio.SeqIO` reads `.ab1` chromatogram files directly — the exact format the sequencing facility hands back. Going from "here's the raw trace from my ant" to a quality-trimmed sequence to a BLAST hit, in about fifteen lines, is a genuinely good first afternoon.

One practical thing to ask the instructor early: whether students get raw sequence data back at all, or just a spreadsheet of IDs. Costa Rica regulates genetic material access fairly tightly, and bats add vertebrate permitting on top. The answer determines whether you're building an analysis environment or a data-exploration one — and it's much better to know before you've provisioned the mini.