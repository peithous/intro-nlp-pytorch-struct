import torchtext.data as data
from torchtext.data import BucketIterator
import torch
from torch import nn
import torch.nn.functional as F
import torch.optim as optim
from torch_struct import LinearChainCRF
#import matplotlib
import matplotlib.pyplot as plt

class ConllXDataset(data.Dataset):
    def __init__(self, path, fields, encoding='utf-8', separator='\t', **kwargs):
        examples = []
        columns = [[], []]
        column_map = {1: 0, 3: 1}
        with open(path, encoding=encoding) as input_file:
            for line in input_file:
                line = line.strip()
                if line == '':
                    examples.append(data.Example.fromlist(columns, fields))
                    columns = [[], []]
                else:
                    for i, column in enumerate(line.split(separator)):
                        if i in column_map:
                            columns[column_map[i]].append(column)
            examples.append(data.Example.fromlist(columns, fields))
        super(ConllXDataset, self).__init__(examples, fields, **kwargs)

# init_token='<bos>', 
WORD = data.Field(pad_token=None) # if pad is included in class vocab, then p (z_t = pad| z_t-1) > 0 
POS = data.Field(pad_token=None, include_lengths=True) #

fields = (('word', WORD), ('pos', POS), (None, None))

#train = ConllXDataset('samIam.conllu', fields)
train_DATA = ConllXDataset('samIam-dataCopies.conllu', fields)
test = ConllXDataset('test.conllu', fields)

WORD.build_vocab(train_DATA) # include 'was' in vocab with <unk> as its POS
POS.build_vocab(train_DATA) 

train_iter = BucketIterator(train_DATA, batch_size=2, device='cpu', shuffle=False)
test_iter = BucketIterator(test, batch_size=2, device='cpu', shuffle=False)


C = len(POS.vocab.itos)
V = len(WORD.vocab.itos)
print(C, V)
print(POS.vocab.stoi)
print(WORD.vocab.stoi)

class Model(nn.Module):
    def __init__(self, voc_size, num_pos_tags):
        super().__init__()
        self.linear = nn.Linear(voc_size, num_pos_tags) # batch x C x V -> batch x C_t x C_t-1
        
    def forward(self, count_mat):
        return F.log_softmax(self.linear(count_mat), dim=1) # normalize C_t given C_t-1 (cols sum to 1)    

model = Model(V, C)
opt = optim.SGD(model.parameters(), lr=0.01)

def show_chain(chain):
    plt.imshow(chain.detach().sum(-1).transpose(0, 1))

def batch_count_mat(sents, pos, length):   
    count_matrix = torch.zeros(sents.shape[1], C, V) 

    for b in range(pos.shape[1]):

        for s in range(length[b]):
            w = sents[s,b]
            ps = pos[s,b]
            count_matrix[b, ps, w] += 1

    #print(count_matrix)    
    return count_matrix


def trn(train_iter):
    
    for epoch in range(100):
        model.train()
#        losses = []
        for i, batch in enumerate(train_iter):
            #model.zero_grad()
            #print(i)
            opt.zero_grad() 
            
            sents = batch.word
            label, lengths = batch.pos

            #print(lengths)

            model_in = batch_count_mat(sents, label, lengths) # batch x C x V -> batch x C_t x C_t-1

            probs = model(model_in)
            #print(probs.shape)
            #for param in model.parameters():
            #    print(i, param) 

            chain = probs.unsqueeze(1).expand(-1, sents.shape[0]-1, -1, -1)  # batch, N, C, C 

            dist = LinearChainCRF(chain) # f(y) = \prod_{n=1}^N \phi(n, y_n, y_n{-1}) 
            #print('d', dist.marginals.shape, dist.marginals)
            #print(dist.argmax.shape) 
            #show_chain(dist.argmax[0])
            #plt.show()

            labels = LinearChainCRF.struct.to_parts(label.transpose(0, 1) \
                        .type(torch.LongTensor), C, lengths=lengths).type(torch.FloatTensor) # b x N x C -> b x (N-1) x C x C 
            #print('l', labels.shape) #labels
            
            #print(dist.log_prob(labels))

            loss = dist.log_prob(labels).sum() # (*sample_shape x batch_shape x event_shape*) -> (*sample_shape x batch_shape*)
            #print(loss)

            (-loss).backward()
            opt.step()
            #losses.append(loss.detach())

        #print(sum(losses))
        
        
        test_losses = []
        for i, batch in enumerate(test_iter):
            model.eval()

            sents = batch.word
            label, lengths = batch.pos
            
            #print(lengths)

            model_in = batch_count_mat(sents, label, lengths) # batch x C x V -> batch x C_t x C_t-1

            probs = model(model_in)
                    #print(probs.shape)
                    #for param in model.parameters():
                    #    print(i, param) 

            chain = probs.unsqueeze(1).expand(-1, sents.shape[0]-1, -1, -1)  # batch, N, C, C 

            dist = LinearChainCRF(chain, lengths=lengths) # f(y) = \prod_{n=1}^N \phi(n, y_n, y_n{-1}) 
            
            #print('label', label.transpose(0, 1)[0])  

            #print('d', dist.marginals.shape, dist.marginals)
            #print(dist.argmax.shape) 

            #show_chain(dist.argmax[0])  
            #plt.show()

            labels = LinearChainCRF.struct.to_parts(label.transpose(0, 1) \
                        .type(torch.LongTensor), C, lengths=lengths).type(torch.FloatTensor) # b x N x C -> b x (N-1) x C x C 
            #print('l', labels.shape, labels)
                    
            #print(dist.log_prob(labels))

            loss = dist.log_prob(labels).sum() # (*sample_shape x batch_shape x event_shape*) -> (*sample_shape x batch_shape*)
            test_losses.append(loss.detach())
            #print(epoch, loss)
            
        # print(test_losses, len(test_losses))
        print(torch.tensor(test_losses).mean())

trn(train_iter)


