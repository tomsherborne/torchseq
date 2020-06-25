from torch.utils.tensorboard import SummaryWriter

from torchseq.utils.singleton import Singleton


writer = None


# TODO: This is all really crappy
def add_to_log(key, value, iteration, run_id, output_path):
    global writer
    if writer is None:
        writer = SummaryWriter(output_path + "/" + run_id + "/logs")

    writer.add_scalar(key, value, iteration)


class Logger(metaclass=Singleton):
    def __init__(self, silent=False, log_path=None):
        self.silent = silent

        if log_path is not None:
            self.writer = SummaryWriter(log_path)

    def add_to_log(self, key, value, iteration):
        self.writer.add_scalar(key, value, iteration)
