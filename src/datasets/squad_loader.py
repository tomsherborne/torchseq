
"""
An example for dataset loaders, starting with data loading including all the functions that either preprocess or postprocess data.
"""
import os
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from datasets.squad_dataset import SquadDataset
from utils.bpe_factory import BPE

class SquadDataLoader:
    def __init__(self, config):
        """
        :param config:
        """
        self.config = config

        train = SquadDataset(os.path.join(config.data_path, 'squad/'), dev=False, test=False)
        valid = SquadDataset(os.path.join(config.data_path, 'squad/'), dev=True, test=False)

        self.len_train_data = len(train)
        self.len_valid_data = len(valid)

        self.train_iterations = (self.len_train_data + self.config.batch_size - 1) // self.config.batch_size
        self.valid_iterations = (self.len_valid_data + self.config.batch_size - 1) // self.config.batch_size


        self.train_loader = DataLoader(train, batch_size=config.batch_size, shuffle=True, num_workers=4, collate_fn=self.pad_and_order_sequences)
        self.valid_loader = DataLoader(valid, batch_size=config.eval_batch_size, shuffle=False, num_workers=4, collate_fn=self.pad_and_order_sequences)

    def pad_and_order_sequences(self, batch):
        keys = batch[0].keys()
        max_lens = {k: max(len(x[k]) for x in batch) for k in keys}

        for x in batch:
            for k in keys:
                if k == 'a_pos':
                    x[k] = F.pad(x[k], (0, max_lens[k]-len(x[k])), value=0)
                else:
                    x[k] = F.pad(x[k], (0, max_lens[k]-len(x[k])), value=BPE.pad_id)

        tensor_batch = {}
        for k in keys:
            tensor_batch[k] = torch.stack([x[k] for x in batch], 0).squeeze()

        return tensor_batch
