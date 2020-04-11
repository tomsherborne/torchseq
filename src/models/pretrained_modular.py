import torch.nn as nn
import torch

import math

from utils.tokenizer import BPE

from models.positional_embeddings import PositionalEncoding

from models.pooling import MultiHeadedPooling

from transformers import BertModel

# def combine_masks(key_padding_mask, attn_mask, targ_size):
#     # targ_size = (bsz, tgt_len, src_len)
#     a = torch.zeros(targ_size)
#     b = torch.zeros(targ_size)
#     if key_padding_mask is not None:  # (bsz, tgt_len) -> targ_size
#         # _check_shapes(key_padding_mask.shape, targ_size[:2])
#         reshaped = key_padding_mask.unsqueeze(2).expand(*targ_size)
#         a[reshaped] = -1e8

#     if attn_mask is not None:  # (tgt_len, src_len) -> targ_size
#         # _check_shapes(attn_mask.shape, targ_size[-2:])
#         b = attn_mask.cpu().unsqueeze(0).expand(*targ_size)
#     return (a + b).unsqueeze(1).clamp(-1e-8,)

# Helper Functions, mostly for making masks
def _check_shapes(shape_1, shape2):
    if shape_1 != shape2:
        raise AssertionError("shape mismatch: {} != {}".format(shape_1, shape2))

LARGE_NEGATIVE = -1e8
def combine_masks(key_padding_mask, causal_lm_mask, targ_size):
    # targ_size = (bsz, tgt_len, src_len)
    a = torch.zeros(targ_size)
    b = torch.zeros(targ_size)
    if key_padding_mask is not None:  # (bsz, tgt_len) -> targ_size
        _check_shapes(key_padding_mask.shape, targ_size[:2])
        reshaped = key_padding_mask.unsqueeze(2).expand(*targ_size)
        a[reshaped] = LARGE_NEGATIVE

    if causal_lm_mask is not None:  # (tgt_len, src_len) -> targ_size
        _check_shapes(causal_lm_mask.shape, targ_size[-2:])
        b = causal_lm_mask.cpu().unsqueeze(0).expand(*targ_size)
    return (a + b).unsqueeze(1).clamp(LARGE_NEGATIVE,)



class PretrainedModularModel(nn.Module):
    def __init__(self, config, src_field='s1', loss=None):
        super().__init__()
        self.config = config

        if 'bart' in self.config.encdec.bert_model:
            from transformers import BartModel
            # from transformers.modelling_bart import _combine_masks as combine_masks

        self.src_field = src_field

        self.loss = loss

        # Embedding layers
        # self.embeddings = nn.Embedding.from_pretrained(torch.Tensor(BPE.embeddings), freeze=config.freeze_embeddings).cpu() # TODO: this should come from a config
        self.embeddings = nn.Embedding(config.prepro.vocab_size, config.raw_embedding_dim).cpu()
        self.embeddings.weight.data = BPE.instance().embeddings
        self.embeddings.weight.requires_grad = not config.freeze_embeddings

        self.embedding_projection = nn.utils.weight_norm(nn.Linear(config.raw_embedding_dim, config.embedding_dim, bias=False))
        

        # Encoder/decoders
        bart_model = BartModel.from_pretrained(config.encdec.bert_model)
        self.encoder = bart_model.encoder
        self.decoder = bart_model.decoder
        self.decoder.generation_mode = False
        

        self.encoder_pooling = MultiHeadedPooling(config.encdec.num_heads, config.embedding_dim, dropout=config.dropout, model_dim_out=config.embedding_dim, use_final_linear=False)

        self.encoder_projection = nn.Linear(config.embedding_dim, config.embedding_dim, bias=False)

        self.output_projection = nn.Linear(config.embedding_dim, config.prepro.vocab_size, bias=False)
        if config.embedding_dim == config.raw_embedding_dim:
            self.output_projection.weight.data = bart_model.shared.weight.data
        

        # self.output_projection = bart_model.lm_head
        self.output_projection.weight.requires_grad = not config.freeze_projection



        for param in self.encoder.parameters():
            param.requires_grad = False
        # for param in self.decoder.parameters():
        #     param.requires_grad = False
        

    def forward(self, batch, output, memory=None, tgt_field=None):

        
        # Re-normalise the projections...
        # with torch.no_grad():
        #     self.embedding_projection.weight_g.div_(self.embedding_projection.weight_g)
        #     if self.config.encdec.data.get('residual', False):
        #         self.encoder_projection.weight_g.div_(self.encoder_projection.weight_g)

        # print(BPE.decode(batch['a'][0][:batch['a_len'][0]]), [BPE.instance().decode([x.item()])  for i,x in enumerate(batch['c'][0]) if batch['a_pos'][0][i].item() > 0], BPE.decode(batch['q'][0][:batch['q_len'][0]]))
        # print([BPE.instance().decode([x.item()])+'/'+str(batch['a_pos'][0][i].item())  for i,x in enumerate(batch['c'][0])])
        # exit()

        # Get some sizes
        max_ctxt_len = batch[self.src_field].shape[1]
        # max_q_len = torch.max(batch['q_len'])
        curr_batch_size = batch[self.src_field].size()[0]
        output_max_len = output.size()[-1]


        context_mask = (torch.arange(max_ctxt_len)[None, :].cpu() >= batch[self.src_field+'_len'][:, None].cpu()).to(self.device)

        bert_context_mask = (~context_mask)
        
        # bert_context_mask = (1.0 - bert_context_mask.long()) * -10000.0

        # First pass? Construct the encoding
        if memory is None:
            src_mask = torch.FloatTensor(max_ctxt_len, max_ctxt_len).fill_(float('-inf') if self.config.directional_masks else 0.0).to(self.device)
            src_mask = torch.triu(src_mask, diagonal=1)
            # src_mask = src_mask.where(batch['a_pos'] > 0, torch.zeros_like(src_mask).unsqueeze(-1))

            
            encoding = self.encoder(input_ids=batch[self.src_field].to(self.device), attention_mask=bert_context_mask)[0] #, token_type_ids=batch['a_pos'].to(self.device)

                
            encoding = encoding.permute(1,0,2) # -> bsz x seq x dim

            

    
            
            # memory = self.encoder_pooling(key=encoding, value=encoding).unsqueeze(1)
            memory = encoding

            # memory = self.encoder_projection(memory)


        # Build some masks
        tgt_mask = torch.FloatTensor(output_max_len, output_max_len).fill_(float('-1e8')).to(self.device)
        # tgt_mask = torch.FloatTensor(output_max_len, output_max_len).fill_(float('0')).to(self.device)
        tgt_mask = torch.triu(tgt_mask, diagonal=1)

        # ie how many indices are non-pad
        output_len = torch.sum(torch.ne(output, BPE.pad_id), dim=-1)

    
        output_pad_mask = (torch.arange(output_max_len)[None, :].cpu() >= output_len[:, None].cpu()).to(self.device)[:, :output_max_len]
        # output_pad_mask = (~output_pad_mask)

        # tgt_mask = None

        bert_tgt_mask = combine_masks(output_pad_mask, tgt_mask, (curr_batch_size, output_max_len, output_max_len)).to(self.device)
        

        # bert_tgt_mask = None

        # print(bert_tgt_mask)
        # print(bert_tgt_mask.shape)
        # print(memory.shape)
        # print(bert_context_mask.shape)
        # print(context_mask.shape)
        # exit()
        # bert_tgt_mask = (~tgt_mask).double()
        
        # bert_tgt_mask = (1.0 - bert_tgt_mask.long()) * -10000.0

        # print(output.shape)
        # print(memory.shape)

        memory_mask = (torch.arange(memory.shape[1])[None, :].cpu() >= batch[self.src_field+'_len'][:, None].cpu()).to(self.device)

        output = self.decoder(
                                output,
                                memory.transpose(0,1),
                                ~memory_mask,
                                bert_tgt_mask
                                # tgt_key_padding_mask=output_pad_mask
                            )

        # print(output[0].shape)

        logits = self.output_projection(output[0])

        # print(torch.argmax(logits, dim=-1))
        # print(batch[self.src_field])
        # exit()
        # logits = output[0]

        # print(memory.shape)
        # print(logits.shape)

        # print('src  ', batch[self.src_field])
        
        # print(output[0].shape)

        loss = None
        
        if tgt_field is not None:
            bos_logits = torch.FloatTensor(curr_batch_size, 1, self.config.prepro.vocab_size).fill_(float('-1e18')).to(self.device)
            bos_logits[:, :, BPE.bos_id] = float('1e18')
            loss_logits = torch.cat([bos_logits, logits], dim=1)
            loss = self.loss(loss_logits.permute(0,2,1), batch[tgt_field])
        
        return logits, memory, loss