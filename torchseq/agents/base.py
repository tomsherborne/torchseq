import logging

import torch

# This project was originally based off this template:
# https://github.com/moemen95/Pytorch-Project-Template


class BaseAgent:
    """
    This base class will contain the base functions to be overloaded by any agent you will implement.
    """

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Agent")

    def set_device(self, use_cuda=True):
        # set cuda flag
        self.cuda_available = torch.cuda.is_available()
        if self.cuda_available and not use_cuda:
            self.logger.warn("You have a CUDA device, so you should probably enable CUDA")

        if use_cuda and not self.cuda_available:
            self.logger.error("Use CUDA is set to true, but not CUDA devices were found!")
            raise Exception("No CUDA devices found")

        self.cuda = self.cuda_available & use_cuda

        if self.cuda:
            self.device = torch.device("cuda")

            self.logger.info("Program will run on *****GPU-CUDA***** ")

            self.model.to(self.device)
            self.loss.to(self.device)

        else:
            self.device = torch.device("cpu")

            self.logger.info("Program will run on *****CPU*****\n")

        if not self.model:
            raise Exception("You need to define your model before calling set_device!")

        self.model.device = self.device

    def load_checkpoint(self, file_name):
        """
        Latest checkpoint loader
        :param file_name: name of the checkpoint file
        :return:
        """
        raise NotImplementedError

    def save_checkpoint(self, file_name="checkpoint.pt", is_best=0):
        """
        Checkpoint saver
        :param file_name: name of the checkpoint file
        :param is_best: boolean flag to indicate whether current checkpoint's metric is the best so far
        :return:
        """
        raise NotImplementedError

    def train(self):
        """
        Main training loop
        :return:
        """
        raise NotImplementedError

    def train_one_epoch(self):
        """
        One epoch of training
        :return:
        """
        raise NotImplementedError

    def validate(self):
        """
        One cycle of model validation
        :return:
        """
        raise NotImplementedError

    def finalize(self):
        """
        Finalizes all the operations of the 2 Main classes of the process, the operator and the data loader
        :return:
        """
        raise NotImplementedError
