#!/bin/bash
#SBATCH --time=3:00:00
#SBATCH --job-name=in_domain
#SBATCH --gres=gpu:1 
#SBATCH --exclude ink-ellie,ink-molly,ink-ron
DATASET=conll
SHOTS=50
PROMPT=multi-classL
TEMPLATE=WRA
TRAIN_SEED=
SAMPLE_SEED=


SEEDED_SUFFIX="${SHOTS}_${SAMPLE_SEED}"
MODEL_NAME="model_${PROMPT}_${TEMPLATE}_${SEEDED_SUFFIX}_${TRAIN_SEED}"


python3 transformers_trainer.py \
  --dataset $DATASET \
  --data_dir dataset/$DATASET \
  --model_folder models/$DATASET/$MODEL_NAME \
  --device cuda:0 \
  --percent_filename_suffix $SEEDED_SUFFIX \
  --prompt $PROMPT \
  --template $TEMPLATE \
  --num_epochs 50 \
  --max_no_incre 10 \
  --seed $TRAIN_SEED
