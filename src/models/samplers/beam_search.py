import torch
import torch.nn as nn

from utils.tokenizer import BPE


def onehot(indexes, N=None, ignore_index=None):
    """
    Creates a one-representation of indexes with N possible entries
    if N is not specified, it will suit the maximum index appearing.
    indexes is a long-tensor of indexes
    ignore_index will be zero in onehot representation
    """
    if N is None:
        N = indexes.max() + 1
    sz = list(indexes.size())
    output = indexes.new().byte().resize_(*sz, N).zero_()
    output.scatter_(-1, indexes.unsqueeze(-1), 1)
    if ignore_index is not None and ignore_index >= 0:
        output.masked_fill_(indexes.eq(ignore_index).unsqueeze(-1), 0)
    return output


class BeamSearchSampler(nn.Module):
    def __init__(self, config, device):
        super(BeamSearchSampler, self).__init__()
        self.config = config
        self.device = device

    def forward(self, model, batch, tgt_field):
        curr_batch_size = batch[[k for k in batch.keys()][0]].size()[0]
        max_output_len = self.config.eval.data.get("max_out_len", 32)

        # TODO: move to config
        beam_width = self.config.beam_search.beam_width  # number of total hypotheses to maintain
        beam_expansion = (
            self.config.beam_search.beam_expansion
        )  # number of new predictions to add to each hypothesis each step

        prevent_repetition = (
            self.config.beam_search.prevent_repetition
            if "prevent_repetition" in self.config.beam_search.data
            else True
        )

        BART_HACK = self.config.eval.data.get("prepend_eos", False)

        # Create vector of SOS + placeholder for first prediction
        output_seq = torch.LongTensor(curr_batch_size, beam_width, 1).fill_(BPE.bos_id).to(self.device)
        scores = torch.FloatTensor(curr_batch_size, beam_width, 1).fill_(0).to(self.device)

        if BART_HACK:
            dummy_token = torch.LongTensor(curr_batch_size, beam_width, 1).fill_(BPE.eos_id).to(self.device)
            output_seq = torch.cat([dummy_token, output_seq], dim=-1)
            scores = torch.cat([scores, scores], dim=-1)

        output_done = torch.BoolTensor(curr_batch_size, beam_width).fill_(False).to(self.device)
        padding = torch.LongTensor(curr_batch_size, beam_width).fill_(BPE.pad_id).to(self.device)
        pad_probs = (
            torch.FloatTensor(curr_batch_size, beam_width, self.config.prepro.vocab_size)
            .fill_(float("-inf"))
            .to(self.device)
        )
        pad_probs[:, :, BPE.pad_id] = float("0")

        def _tile_batch(x):
            return x.repeat_interleave(beam_width, dim=0)

        batch_tiled = {k: _tile_batch(x) for k, x in batch.items() if k[-5:] != "_text"}

        seq_ix = 0
        memory = None
        while torch.sum(output_done) < curr_batch_size * beam_width and seq_ix < max_output_len:

            new_logits, memory = model(batch_tiled, output_seq.view(curr_batch_size * beam_width, -1), memory)
            new_logits = new_logits.view(curr_batch_size, beam_width, -1, self.config.prepro.vocab_size)
            output_done = (output_seq[:, :, -1] == BPE.pad_id) | (output_seq[:, :, -1] == BPE.eos_id)

            if prevent_repetition:
                one_hot_prev = onehot(output_seq[:, :, -1], N=self.config.prepro.vocab_size)
                new_logits[:, :, -1, :] = new_logits[:, :, -1, :] + (one_hot_prev * float("-1e-16"))

            new_probs = torch.where(
                output_done.unsqueeze(-1), pad_probs, torch.log_softmax(new_logits[:, :, -1, :], -1)
            )

            if seq_ix == 0:
                top_expansions = torch.topk(new_probs, k=beam_width, dim=-1, largest=True)

                # On first iteration, the beams are all the same! So spread the topk across beams
                output_seq = torch.cat(
                    [output_seq, top_expansions.indices.unsqueeze(2)[:, 0, :, :].permute(0, 2, 1)], dim=-1
                )
                scores = torch.cat([scores, top_expansions.values.unsqueeze(2)[:, 0, :, :].permute(0, 2, 1)], dim=-1)
                # print(scores)
                # exit()
            else:

                top_expansions = torch.topk(new_probs, k=beam_expansion, dim=-1, largest=True)

                expanded_beam_ixs = torch.cat(
                    [
                        output_seq.unsqueeze(-2).expand(-1, -1, beam_expansion, -1),
                        top_expansions.indices.unsqueeze(-1),
                    ],
                    dim=-1,
                )
                expanded_beam_scores = torch.cat(
                    [scores.unsqueeze(-2).expand(-1, -1, beam_expansion, -1), top_expansions.values.unsqueeze(-1)],
                    dim=-1,
                )

                curr_seq_len = expanded_beam_ixs.shape[3]

                expanded_beam_ixs = expanded_beam_ixs.view(curr_batch_size, beam_width * beam_expansion, curr_seq_len)

                hypothesis_len = torch.sum(expanded_beam_ixs != BPE.pad_id, dim=-1)
                # Length penalty needs to be applied to *overall* score, not score for this token
                len_alpha = self.config.beam_search.length_alpha
                length_penalty = torch.pow((5 + hypothesis_len).float(), len_alpha) / pow(5.0 + 1.0, len_alpha)

                expanded_beam_scores = expanded_beam_scores.view(
                    curr_batch_size, beam_width * beam_expansion, curr_seq_len
                )

                expanded_beam_scores = expanded_beam_scores

                beam_scores = torch.sum(expanded_beam_scores, dim=-1).to(scores) / length_penalty

                top_beams = torch.topk(beam_scores, k=beam_width, dim=-1)

                scores = torch.gather(
                    expanded_beam_scores, 1, top_beams.indices.unsqueeze(-1).expand(-1, -1, curr_seq_len)
                )
                new_output = torch.gather(
                    expanded_beam_ixs, 1, top_beams.indices.unsqueeze(-1).expand(-1, -1, curr_seq_len)
                )

                # Use pad for the output for elements that have completed
                output_done = (new_output[:, :, -2] == BPE.eos_id) | (new_output[:, :, -2] == BPE.pad_id)
                new_output[:, :, -1] = torch.where(output_done, padding, new_output[:, :, -1])

                output_seq = new_output

            seq_ix += 1

        # Sort by score

        if BART_HACK:
            output_seq = output_seq[:, :, 1:]
            scores = scores[:, :, 1:]

        output_len = torch.sum(output_seq != BPE.pad_id, dim=-1)
        length_penalty = torch.pow((5 + output_len).float(), len_alpha) / pow(5.0 + 1.0, len_alpha)
        beam_scores = torch.sum(scores, dim=-1) / length_penalty

        sorted_scores, sorted_indices = torch.sort(beam_scores, descending=True)

        output_seq = torch.gather(output_seq, 1, sorted_indices.unsqueeze(-1).expand(-1, -1, output_seq.shape[2]))

        return output_seq, sorted_scores, output_len
