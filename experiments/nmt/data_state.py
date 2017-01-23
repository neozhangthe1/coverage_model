dict(
source=["/home/yzhang3151/project/NMT/experiments/nmt/binarized_text.diag.shuf.h5"],
target=["/home/yzhang3151/project/NMT/experiments/nmt/binarized_text.drug.shuf.h5"],
indx_word="/home/yzhang3151/project/NMT/experiments/nmt/ivocab.diag.pkl",
indx_word_target="/home/yzhang3151/project/NMT/experiments/nmt/ivocab.drug.pkl",
word_indx="/home/yzhang3151/project/NMT/experiments/nmt/vocab.diag.pkl",
word_indx_trgt="/home/yzhang3151/project/NMT/experiments/nmt/vocab.drug.pkl",
null_sym_source=8360,
null_sym_target=1010,
n_sym_source=16001,
n_sym_target=16001,
loopIters=1000000,
seqlen=50,
bs=80,
dim=1000,
saveFreq=30,
last_forward = False,
forward = True,
backward = True,
last_backward = False,

use_context_gate=True,

##########
# for coverage
maintain_coverage=True,
# for linguistic coverage, the dim can only be 1
coverage_dim=10,

#-----------------------
use_linguistic_coverage=False,
# added by Zhaopeng Tu, 2015-12-16
use_fertility_model=True,
max_fertility=2,
coverage_accumulated_operation = "additive",
##########
use_recurrent_coverage=True,
use_recurrent_gating_coverage=True,
use_probability_for_recurrent_coverage=True,
use_input_annotations_for_recurrent_coverage=True,
use_decoding_state_for_recurrent_coverage=True,
)
