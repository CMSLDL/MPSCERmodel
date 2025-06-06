# 
# @author: Allan
#

import random
from tqdm import tqdm
from typing import List, Dict
# from sentence_transformers import SentenceTransformer, util
import torch
from torch.utils.data import Dataset
from torch.utils.data._utils.collate import default_collate
from transformers import PreTrainedTokenizer
import collections
import numpy as np
from termcolor import colored
from scipy import stats
from src.data.data_utils import convert_iobes, build_label_idx, check_all_labels_in_dict
import bert_score
from src.data import Instance
from src.data.search_space_manager import SearchSpaceManager
import sys

Feature = collections.namedtuple('Feature', 'input_ids attention_mask token_type_ids orig_to_tok_index word_seq_len label_ids')
Feature.__new__.__defaults__ = (None,) * 6

def entities_num(itm):
    lis = []
    temp = itm.entities
    for te in temp:
        if te[1] not in lis:
            lis.append(te[1])
    return len(lis)
    
def Weight_Random_Algorithm(numbers, decay_factor):
    if len(numbers) <= 1:
        raise ValueError("The sequence must have more than one number")

    max_value = max(numbers)
    target_idx = numbers.index(max_value)


    updated_numbers = numbers.copy()
    original_value = updated_numbers[target_idx]
    decayed_value = original_value * decay_factor
    delta = original_value - decayed_value
    updated_numbers[target_idx] = decayed_value
    distribute = delta / (len(numbers) - 1)
    for i in range(len(numbers)):
        if i != target_idx:
            updated_numbers[i] += distribute

    return updated_numbers

def maybe_show_prompt(id, word, prompt, mod):
    if id % mod == 0:
        print(colored(f"Instance {id}: {word}", "blue"))
        print(colored(f"Prompt {id}: {prompt}\n", "yellow"))

def convert_instances_to_feature_tensors(instances: List[Instance],
                                         tokenizer: PreTrainedTokenizer,
                                         label2idx: Dict[str, int],
                                         algorithm: str = None, # "max", "random", "sbert", "bertscore"
                                         template: str = None, # "no_context", "context", "context_all", "structure", "structure_all"
                                         prompt_candidates_from_outside: List[str] = None,
                                         constrained_instances: bool = False):
    
    
    features = []
    candidates = [] # usually whole train dataset = prompt_candidates_from_outside

    if prompt_candidates_from_outside is not None and prompt is not None:
        candidates = prompt_candidates_from_outside
    else:
        candidates = instances

    ## Construct entity dictionary for "max" or "random".
    entity_dict = {}
    for inst in candidates:
        for entity, label in inst.entities:
            if label not in entity_dict:
                entity_dict[label] = {}
            if entity not in entity_dict[label]:
                entity_dict[label][entity] = [inst]
            else:
                entity_dict[label][entity].append(inst)

    ## Popular Entity
    if prompt == "max":
        max_entities = {}
        for label in entity_dict:
            cha_x = ()
            itms = entity_dict[label].items()
            ori_itm = list(itms)[0]
            entity_num = entities_num(tuple(ori_itm[1])[0])
            cha_x = ori_itm
            for temp in entity_dict[label].items():
                te = tuple(temp[1])[0]
                num = entities_num(te)
                if num>entity_num:
                    cha_x = temp
                max_entities[label] = [cha_x[0], tuple(cha_x[1])[0]]


    for idx, inst in enumerate(instances):
        words = inst.ori_words
        orig_to_tok_index = []
        tokens = []
        for i, word in enumerate(words):
            orig_to_tok_index.append(len(tokens))
            word_tokens = tokenizer.tokenize(" " + word)
            for sub_token in word_tokens:
                tokens.append(sub_token)
        labels = inst.labels
        label_ids = [label2idx[label] for label in labels] if labels else [-100] * len(words)

        if prompt is None:
            input_ids = tokenizer.convert_tokens_to_ids([tokenizer.cls_token] + tokens + [tokenizer.sep_token])
        elif prompt == "max":
            prompt_tokens = []
            for entity_label in max_entities:
                if template in ["structure", "structure_all",'lexical','lexical_all','lexical_search_one']:
                    instance_prompt_tokens = []
                    instance_words = max_entities[entity_label][1].ori_words
                    for i, word in enumerate(instance_words):
                        instance_tokens = tokenizer.tokenize(" " + word)
                        for sub_token in instance_tokens:
                            instance_prompt_tokens.append(sub_token)

                    if template == "structure":
                        entity_tokens = tokenizer.tokenize(" " + max_entities[entity_label][0])
                        start_ind = instance_prompt_tokens.index(entity_tokens[0])
                        end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                        instance_prompt_tokens.insert(end_ind + 1, ']')
                        instance_prompt_tokens.insert(end_ind + 1, entity_label)
                        instance_prompt_tokens.insert(end_ind + 1, '|')
                        instance_prompt_tokens.insert(start_ind, '[')

                    elif template == "structure_all":
                        for entity in max_entities[entity_label][1].entities:
                            entity_tokens = tokenizer.tokenize(" " + entity[0])
                            start_ind = instance_prompt_tokens.index(entity_tokens[0])
                            end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                            instance_prompt_tokens.insert(end_ind + 1, ']')
                            instance_prompt_tokens.insert(end_ind + 1, entity[1])
                            instance_prompt_tokens.insert(end_ind + 1, '|')
                            instance_prompt_tokens.insert(start_ind, '[')
                    
                    elif template =='lexical':
                        entity_tokens = tokenizer.tokenize(" " + max_entities[entity_label][0])
                        start_ind = instance_prompt_tokens.index(entity_tokens[0])
                        end_ind = instance_prompt_tokens.index(entity_tokens[-1])

                        instance_prompt_tokens[start_ind] = entity_label
                        del instance_prompt_tokens[start_ind+1:end_ind+1]

                    
                    elif template=='lexical_all':
                        for entity in max_entities[entity_label][1].entities:
                            entity_tokens = tokenizer.tokenize(" " + entity[0])
                            start_ind = instance_prompt_tokens.index(entity_tokens[0])
                            end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                            instance_prompt_tokens[start_ind] = entity[1]
                            del instance_prompt_tokens[start_ind + 1:end_ind + 1]
                    elif template=='lexical_search_one':
                        len_entity = len(max_entities[entity_label][1].entities)
                        entities = max_entities[entity_label][1].entities
                        randnum = random.randint(0,len_entity-1)
                        # print(entities)
                        # print(randnum)
                        entity = entities[randnum]
                        entity_tokens = tokenizer.tokenize(" " + entity[0])
                        start_ind = instance_prompt_tokens.index(entity_tokens[0])
                        end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                        instance_prompt_tokens[start_ind] = entity[1]
                        del instance_prompt_tokens[start_ind + 1:end_ind + 1]

                    prompt_tokens.extend(instance_prompt_tokens)
                    prompt_tokens.append(tokenizer.sep_token)

            maybe_show_prompt(idx, words, prompt_tokens, step_sz)
            input_ids = tokenizer.convert_tokens_to_ids([tokenizer.cls_token] + tokens + [tokenizer.sep_token] + prompt_tokens)

        elif prompt == "random":
            prompt_tokens = []
            for entity_label in entity_dict:
                if template in ["no_context", "context", "context_all"]:
                    entity = random.choice(tuple(entity_dict[entity_label]))
                    instance = random.choice(entity_dict[entity_label][entity])

                    if template in ["context", "context_all"]:
                        instance_words = instance.ori_words
                        for i, word in enumerate(instance_words):
                            instance_tokens = tokenizer.tokenize(" " + word)
                            for sub_token in instance_tokens:
                                prompt_tokens.append(sub_token)

                    if template in ["no_context", "context"]:
                        entity_tokens = tokenizer.tokenize(" " + entity)
                        for sub_token in entity_tokens:
                            prompt_tokens.append(sub_token)

                        prompt_tokens.append("is")
                        prompt_tokens.append(entity_label)
                        prompt_tokens.append(".")
                        prompt_tokens.append(tokenizer.sep_token)

                    elif template in ["context_all"]:
                        for entity in instance.entities:
                            entity_tokens = tokenizer.tokenize(" " + entity[0])
                            for sub_token in entity_tokens:
                                prompt_tokens.append(sub_token)

                            prompt_tokens.append("is")
                            prompt_tokens.append(entity[1])
                            prompt_tokens.append(".")
                        prompt_tokens.append(tokenizer.sep_token)

                if template in ["structure", "structure_all","lexical","lexical_all"]:
                    entity = random.choice(tuple(entity_dict[entity_label]))
                    instance = random.choice(entity_dict[entity_label][entity])

                    instance_prompt_tokens = []
                    instance_words = instance.ori_words
                    for i, word in enumerate(instance_words):
                        instance_tokens = tokenizer.tokenize(" " + word)
                        for sub_token in instance_tokens:
                            instance_prompt_tokens.append(sub_token)


                    if template == "structure":
                        entity_tokens = tokenizer.tokenize(" " + entity)
                        start_ind = instance_prompt_tokens.index(entity_tokens[0])
                        end_ind = instance_prompt_tokens.index(entity_tokens[-1])

                        instance_prompt_tokens.insert(end_ind + 1, ']')
                        instance_prompt_tokens.insert(end_ind + 1, entity_label)
                        instance_prompt_tokens.insert(end_ind + 1, '|')
                        instance_prompt_tokens.insert(start_ind, '[')

                    elif template == "structure_all":
                        for entity in instance.entities:
                            entity_tokens = tokenizer.tokenize(" " + entity[0])
                            start_ind = instance_prompt_tokens.index(entity_tokens[0])
                            end_ind = instance_prompt_tokens.index(entity_tokens[-1])

                            instance_prompt_tokens.insert(end_ind + 1, ']')
                            instance_prompt_tokens.insert(end_ind + 1, entity[1])
                            instance_prompt_tokens.insert(end_ind + 1, '|')
                            instance_prompt_tokens.insert(start_ind, '[')

                    elif template =='lexical':
                        entity_tokens = tokenizer.tokenize(" " + entity)
                        start_ind = instance_prompt_tokens.index(entity_tokens[0])
                        end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                        instance_prompt_tokens[start_ind] = entity_label
                        del instance_prompt_tokens[start_ind + 1:end_ind + 1]

                    elif template=='lexical_all':
                        for entity in instance.entities:
                            entity_tokens = tokenizer.tokenize(" " + entity[0])
                            start_ind = instance_prompt_tokens.index(entity_tokens[0])
                            end_ind = instance_prompt_tokens.index(entity_tokens[-1])
                            instance_prompt_tokens[start_ind] = entity[1]
                            del instance_prompt_tokens[start_ind + 1:end_ind + 1]

                    prompt_tokens.extend(instance_prompt_tokens)
                    prompt_tokens.append(tokenizer.sep_token)

            maybe_show_prompt(idx, words, prompt_tokens, step_sz)
            input_ids = tokenizer.convert_tokens_to_ids([tokenizer.cls_token] + tokens + [tokenizer.sep_token] + prompt_tokens)

        segment_ids = [0] * len(input_ids)
        input_mask = [1] * len(input_ids)

        if len(input_ids) > 512:
            continue
        else:
            features.append(Feature(input_ids=input_ids,
                                    attention_mask=input_mask,
                                    orig_to_tok_index=orig_to_tok_index,
                                    token_type_ids=segment_ids,
                                    word_seq_len=len(orig_to_tok_index),
                                    label_ids=label_ids))

    if prompt_candidates_from_outside is None and (prompt == "sbert" or prompt == "bertscore"):
        print(colored("[Info] Top 1 selection precision: %.2f" % (top_k_correct_selection_count / len(instances)), 'yellow'))

    if len(scores) > 0 and (prompt == "sbert" or prompt == "bertscore"):
        print("[debug] Score Stats:", stats.describe(scores))
        print("[debug] Scores:", scores)
        print("##################################")

    if prompt_candidates_from_outside is None and prompt is not None:
        return features, candidates
    else:
        return features

class TransformersNERDataset(Dataset):

    def __init__(self, file: str,
                 tokenizer: PreTrainedTokenizer,
                 is_train: bool,
                 sents: List[List[str]] = None,
                 label2idx: Dict[str, int] = None,
                 number: int = -1,
                 percentage: int = 100,
                 prompt: str = None,
                 template: str = None,
                 prompt_candidates_from_outside: List[str] = None):
        """
        sents: we use sentences if we want to build dataset from sentences directly instead of file
        """
        ## read all the instances. sentences and labels
        self.percentage = percentage
        insts = self.read_txt(file=file, number=number) if sents is None else self.read_from_sentences(sents)
        self.insts = insts
        if is_train:
            print(f"[Data Info] Using the training set to build label index")
            assert label2idx is None
            ## build label to index mapping. e.g., B-PER -> 0, I-PER -> 1
            idx2labels, label2idx = build_label_idx(insts)
            self.idx2labels = idx2labels
            self.label2idx = label2idx
        else:
            assert label2idx is not None ## for dev/test dataset we don't build label2idx
            self.label2idx = label2idx
            # check_all_labels_in_dict(insts=insts, label2idx=self.label2idx)

        if is_train and prompt is not None:
            self.insts_ids, self.prompt_candidates = convert_instances_to_feature_tensors(insts, tokenizer, label2idx, prompt=prompt, template=template)
        else:
            self.insts_ids = convert_instances_to_feature_tensors(insts, tokenizer, label2idx, prompt=prompt, template=template, prompt_candidates_from_outside=prompt_candidates_from_outside)
            self.prompt_candidates = None
        self.tokenizer = tokenizer


    def read_from_sentences(self, sents: List[List[str]]):
        """
        sents = [['word_a', 'word_b'], ['word_aaa', 'word_bccc', 'word_ccc']]
        """
        insts = []
        for sent in sents:
            insts.append(Instance(words=sent, ori_words=sent))
        return insts


    def read_txt(self, file: str, number: int = -1) -> List[Instance]:
        print(f"[Data Info] Reading file: {file}, labels will be converted to IOBES encoding")
        print(f"[Data Info] Modify src/data/transformers_dataset.read_txt function if you have other requirements")
        insts = []
        with open(file, 'r', encoding='utf-8') as f:
            words = []
            ori_words = []
            labels = []
            entities = []
            entity = []
            entity_label = []
            for line in tqdm(f.readlines()):
                line = line.rstrip()
                if line == "":
                    labels = convert_iobes(labels)
                    if len(entity) != 0:
                        entities.append([" ".join(entity),entity_label[0]])
                    if len(set(labels)) > 1:
                        insts.append(Instance(words=words, ori_words=ori_words, labels=labels, entities=entities))
                    words = []
                    ori_words = []
                    labels = []
                    entities = []
                    entity = []
                    entity_label = []
                    if len(insts) == number:
                        break
                    continue
                ls = line.split()
                word, label = ls[0],ls[-1]
                ori_words.append(word)
                words.append(word)
                labels.append(label)

                if label.startswith("B"):
                    entity.append(word)
                    entity_label.append(label.split('-')[1])
                elif label.startswith("I"):
                    entity.append(word)
                else:
                    if len(entity) != 0:
                        entities.append([" ".join(entity), entity_label[0]])
                        entity = []
                        entity_label = []

        numbers = int(len(insts) * self.percentage / 100)
        percentage_insts = insts[:numbers]

        print("number of sentences: {}".format(len(percentage_insts)))
        return percentage_insts

    def __len__(self):
        return len(self.insts_ids)

    def __getitem__(self, index):
        return self.insts_ids[index]

    def collate_fn(self, batch:List[Feature]):
        word_seq_len = [len(feature.orig_to_tok_index) for feature in batch]
        max_seq_len = max(word_seq_len)
        max_wordpiece_length = max([len(feature.input_ids) for feature in batch])
        for i, feature in enumerate(batch):
            padding_length = max_wordpiece_length - len(feature.input_ids)
            input_ids = feature.input_ids + [self.tokenizer.pad_token_id] * padding_length
            mask = feature.attention_mask + [0] * padding_length
            type_ids = feature.token_type_ids + [self.tokenizer.pad_token_type_id] * padding_length
            padding_word_len = max_seq_len - len(feature.orig_to_tok_index)
            orig_to_tok_index = feature.orig_to_tok_index + [0] * padding_word_len
            label_ids = feature.label_ids + [0] * padding_word_len

            batch[i] = Feature(input_ids=np.asarray(input_ids),
                               attention_mask=np.asarray(mask), token_type_ids=np.asarray(type_ids),
                               orig_to_tok_index=np.asarray(orig_to_tok_index),
                               word_seq_len =feature.word_seq_len,
                               label_ids=np.asarray(label_ids))
        results = Feature(*(default_collate(samples) for samples in zip(*batch)))
        return results
