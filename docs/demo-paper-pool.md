# ClaimBench Demo Paper Pool

This note tracks credible papers for a public ClaimBench demo. The goal is to avoid a cache-only demo and show real uncached execution for compute-feasible ML papers.

## Demo Positioning

ClaimBench should be presented as a reproducibility auditor for scoped, compute-aware claims:

- It can run real paper code in a declared environment.
- It can fetch or use public datasets when the setup is reasonable.
- It can parse generated metrics and compare them against paper claims.
- It can produce logs, artifacts, failure categories, and a report.
- It should not promise full reproduction of extremely expensive pretraining papers such as RoBERTa from scratch.

## Strong Live Candidates

These are the best first targets for uncached Docker runs.

1. ROCKET: Exceptionally fast and accurate time series classification using random convolutional kernels
   - Paper: https://arxiv.org/abs/1910.13051
   - Code: https://github.com/angus924/rocket
   - Why: official code, CPU-friendly, benchmark-oriented, public UCR datasets.

2. MINIROCKET: A Very Fast Almost Deterministic Transform for Time Series Classification
   - Paper: https://arxiv.org/abs/2012.08791
   - Code: https://github.com/angus924/minirocket
   - Why: very fast CPU runs and strong reproducibility story.

3. LIBLINEAR: A Library for Large Linear Classification
   - Paper/code: https://www.csie.ntu.edu.tw/~cjlin/liblinear/
   - Why: official code, small benchmark datasets, fast CPU execution.

4. LIBSVM: A Library for Support Vector Machines
   - Paper/code: https://www.csie.ntu.edu.tw/~cjlin/libsvm/
   - Why: official code, classic ML, small datasets, clear metrics.

5. fastText: Enriching Word Vectors with Subword Information
   - Paper: https://arxiv.org/abs/1607.04606
   - Code: https://github.com/facebookresearch/fastText
   - Why: official CLI, CPU-friendly for bounded text classification or embedding runs.

## Good Prepared Manifest Candidates

These can broaden the catalog, but need more vetting before live demo use.

6. MultiROCKET
   - Paper: https://arxiv.org/abs/2102.00457
   - Why: natural continuation of ROCKET/MINIROCKET, likely feasible with careful setup.

7. UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction
   - Paper: https://arxiv.org/abs/1802.03426
   - Code: https://github.com/lmcinnes/umap
   - Why: official implementation and small dataset demos are feasible.

8. HDBSCAN
   - Code: https://github.com/scikit-learn-contrib/hdbscan
   - Why: CPU-friendly clustering, but metric choice must be precise.

9. LeNet / Backpropagation Applied to Handwritten Zip Code Recognition
   - Reproduction code: https://github.com/karpathy/lecun1989-repro
   - Why: real historical ML reproduction with manageable CPU runtime.

10. GloVe: Global Vectors for Word Representation
    - Paper: https://nlp.stanford.edu/pubs/glove.pdf
    - Code: https://github.com/stanfordnlp/GloVe
    - Why: official code, but exact full paper results need larger corpora.

11. word2vec: Efficient Estimation of Word Representations in Vector Space
    - Paper: https://arxiv.org/abs/1301.3781
    - Code: https://github.com/tmikolov/word2vec
    - Why: official code, but exact paper numbers depend heavily on corpus setup.

12. Isolation Forest
    - Paper: https://cs.nju.edu.cn/zhouzh/zhouzh.files/publication/icdm08b.pdf
    - Why: feasible anomaly detection benchmarks, but needs an appropriate reference implementation.

13. t-SNE: Visualizing Data using t-SNE
    - Paper: https://www.jmlr.org/papers/v9/vandermaaten08a.html
    - Why: classic ML paper, but exact qualitative claims are harder to score automatically.

## Recommended Build Order

1. Make one uncached `run-paper` demo pass end to end.
2. Promote ROCKET as the first real public demo paper.
3. Add LIBLINEAR or LIBSVM as a second live candidate because they are official, classic, and lightweight.
4. Add fastText as the first NLP live candidate.
5. Expand the catalog to 10-15 manifests, clearly marking which are live-ready and which require longer setup.

## Demo Rule

For public demos, at least one paper should be run with:

```bash
PYTHONPATH=src python -m claimbench.cli run-paper <manifest> --sandbox docker --output-dir runs/<paper_id>
```

The report shown in the dashboard should come from newly generated run artifacts, not from manifest `cached_runs`.
