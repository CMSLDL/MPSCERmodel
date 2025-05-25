The code is for **Multi-class Label Prompt Selecting and Core Entity Replacing Based Named Entity Recognition**

### Setup

1. Run `pip install -r requirements.txt`

2. _*Optional*_ Add support for CUDA. We have tested the repository on pytorch
   version [1.7.1](https://pytorch.org/get-started/previous-versions/#v171) with CUDA version 10.1.

```bash
# conda
conda install pytorch==1.7.1 torchvision==0.8.2 torchaudio==0.7.2 cudatoolkit=10.1 -c pytorch

# pip
pip install torch==1.7.1+cu101 torchvision==0.8.2+cu101 torchaudio==0.7.2 -f https://download.pytorch.org/whl/torch_stable.html
```

## Valid Combination Table

| Prompt       | algorithm | Description                                                  |
| ------------ | -------- | ------------------------------------------------------------ |
| multi-class  | random   | Multi-class Selection Demonstration+Core Entity Replacing    |
| multi-class  | WRA      | Multi-class Selection+Core Entity Replacing with **W**eight **R**andom **A**lgorithm |
| multi-classL | random   | Low Multi-class Selection with Low-Core-Entity Demonstration +Core Entity Replacing |
| multi-classL | WRA      | Low Multi-class Selection with Low-Core-Entity Demonstration +Core Entity Replacing with **W**eight **R**andom **A**lgorithm |



### How to use 

bash run.sh <DATASET> <SHOT> <PROMPT> <TEMPLATE> <TRAIN_SEED> <SAMPLE_SEED>
