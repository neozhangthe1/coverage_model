#!/usr/bin/env python

import argparse
import pickle
import traceback
import logging
import time
import sys

import numpy

import experiments.nmt
from experiments.nmt import\
    RNNEncoderDecoder,\
    prototype_state,\
    prototype_search_with_coverage_state,\
    parse_input

from experiments.nmt.numpy_compat import argpartition

logger = logging.getLogger(__name__)

class Timer(object):

    def __init__(self):
        self.total = 0

    def start(self):
        self.start_time = time.time()

    def finish(self):
        self.total += time.time() - self.start_time

class BeamSearch(object):

    def __init__(self, enc_dec):
        self.enc_dec = enc_dec
        state = self.enc_dec.state
        self.eos_id = state['null_sym_target']
        self.unk_id = state['unk_sym_target']

    def compile(self):
        self.comp_repr = self.enc_dec.create_representation_computer()
        # added by Zhaopeng Tu, 2015-12-17, for fertility
        if self.enc_dec.state['maintain_coverage'] and self.enc_dec.state['use_linguistic_coverage'] and self.enc_dec.state['use_fertility_model']:
            self.comp_fert = self.enc_dec.create_fertility_computer()
        self.comp_init_states = self.enc_dec.create_initializers()
        self.comp_next_probs = self.enc_dec.create_next_probs_computer()
        self.comp_next_states = self.enc_dec.create_next_states_computer()

    def search(self, seq, n_samples, ignore_unk=False, minlen=1):
        c = self.comp_repr(seq)[0]
        states = [x[None, :] for x in self.comp_init_states(c)]
        dim = states[0].shape[1]
        # added by Zhaopeng Tu, 2015-11-02
        if self.enc_dec.state['maintain_coverage']:
            coverage_dim = self.enc_dec.state['coverage_dim']
            if self.enc_dec.state['use_linguistic_coverage'] and self.enc_dec.state['coverage_accumulated_operation'] == 'subtractive':
                coverages = numpy.ones((c.shape[0], 1, coverage_dim), dtype='float32')
            else:
                coverages = numpy.zeros((c.shape[0], 1, coverage_dim), dtype='float32')
            fin_coverages = []
        else:
            coverages = None
        
        if self.enc_dec.state['maintain_coverage'] and self.enc_dec.state['use_linguistic_coverage'] and self.enc_dec.state['use_fertility_model']:
            fertility = self.comp_fert(c)
        else:
            fertility = None

        num_levels = len(states)

        fin_trans = []
        fin_costs = []
        fin_aligns = []

        trans = [[]]
        aligns = [[]]
        costs = [0.0]

        for k in range(3 * len(seq)):
            if n_samples == 0:
                break

            # Compute probabilities of the next words for
            # all the elements of the beam.
            beam_size = len(trans)
            last_words = (numpy.array([t[-1] for t in trans])
                    if k > 0
                    else numpy.zeros(beam_size, dtype="int64"))
            results = self.comp_next_probs(c, k, last_words, *states, coverage_before=coverages, fertility=fertility)
            log_probs = numpy.log(results[0])
            # alignment shape: (source_len, beam_size)
            alignment = results[1]

            # Adjust log probs according to search restrictions
            if ignore_unk:
                log_probs[:,self.unk_id] = -numpy.inf
            # TODO: report me in the paper!!!
            if k < minlen:
                log_probs[:,self.eos_id] = -numpy.inf

            # Find the best options by calling argpartition of flatten array
            next_costs = numpy.array(costs)[:, None] - log_probs
            flat_next_costs = next_costs.flatten()
            best_costs_indices = argpartition(
                    flat_next_costs.flatten(),
                    n_samples)[:n_samples]

            # Decypher flatten indices
            voc_size = log_probs.shape[1]
            trans_indices = best_costs_indices / voc_size
            word_indices = best_costs_indices % voc_size
            costs = flat_next_costs[best_costs_indices]

            # Form a beam for the next iteration
            new_trans = [[]] * n_samples

            new_aligns = [[]] * n_samples
            new_costs = numpy.zeros(n_samples)
            new_states = [numpy.zeros((n_samples, dim), dtype="float32") for level
                    in range(num_levels)]
            inputs = numpy.zeros(n_samples, dtype="int64")
            if self.enc_dec.state['maintain_coverage']:
                new_coverages = numpy.zeros((c.shape[0], n_samples, coverage_dim), dtype='float32')
            else:
                new_coverages = None
            for i, (orig_idx, next_word, next_cost) in enumerate(
                    zip(trans_indices, word_indices, costs)):
                new_trans[i] = trans[orig_idx] + [next_word]
                # alignment shape: (source_len, beam_size)
                new_aligns[i] = aligns[orig_idx] + [alignment[:,orig_idx]]
                new_costs[i] = next_cost
                for level in range(num_levels):
                    new_states[level][i] = states[level][orig_idx]
                inputs[i] = next_word
                if self.enc_dec.state['maintain_coverage']:
                    new_coverages[:,i,:] = coverages[:,orig_idx,:]
            new_states = self.comp_next_states(c, k, inputs, *new_states, coverage_before=new_coverages, fertility=fertility)
            if self.enc_dec.state['maintain_coverage']:
                new_coverages = new_states[-1]
                new_states = new_states[:-1]

            # Filter the sequences that end with end-of-sequence character
            trans = []
            aligns = []
            costs = []
            indices = []
            for i in range(n_samples):
                if new_trans[i][-1] != self.enc_dec.state['null_sym_target']:
                    trans.append(new_trans[i])
                    aligns.append(new_aligns[i])
                    costs.append(new_costs[i])
                    indices.append(i)
                else:
                    n_samples -= 1
                    fin_trans.append(new_trans[i])
                    fin_aligns.append(new_aligns[i])
                    fin_costs.append(new_costs[i])
                    if self.enc_dec.state['maintain_coverage']:
                        fin_coverages.append(new_coverages[:,i,0])
            states = [x[indices] for x in new_states]

            if self.enc_dec.state['maintain_coverage']:
                coverages = numpy.zeros((c.shape[0], n_samples, coverage_dim), dtype='float32')
                for i in range(n_samples):
                    coverages[:,i,:] = new_coverages[:, indices[i], :]

        # Dirty tricks to obtain any translation
        if not len(fin_trans):
            if ignore_unk:
                logger.warning("Did not manage without UNK")
                return self.search(seq, n_samples, False, minlen)
            elif n_samples < 100:
                logger.warning("Still no translations: try beam size {}".format(n_samples * 2))
                return self.search(seq, n_samples * 2, False, minlen)
            else:
                fin_trans = trans
                fin_aligns = aligns
                fin_costs = costs
                if self.enc_dec.state['maintain_coverage']:
                    fin_coverages = coverages[:,:,0].transpose().tolist()
                logger.error("Translation failed")

        fin_trans = numpy.array(fin_trans)[numpy.argsort(fin_costs)]
        fin_aligns = numpy.array(fin_aligns)[numpy.argsort(fin_costs)]
        if self.enc_dec.state['maintain_coverage']:
            fin_coverages = numpy.array(fin_coverages)[numpy.argsort(fin_costs)]
        fin_costs = numpy.array(sorted(fin_costs))

        if self.enc_dec.state['maintain_coverage']:
            if self.enc_dec.state['use_linguistic_coverage'] and self.enc_dec.state['use_fertility_model']:
                return fin_trans, fin_aligns, fin_costs, fin_coverages, fertility
            else:
                return fin_trans, fin_aligns, fin_costs, fin_coverages
        else:
            return fin_trans, fin_aligns, fin_costs

def indices_to_words(i2w, seq):
    sen = []
    for k in range(len(seq)):
        if i2w[seq[k]] == '<eol>':
            break
        sen.append(i2w[seq[k]])
    return sen

def sample(lm_model, seq, n_samples,
        sampler=None, beam_search=None,
        ignore_unk=False, normalize=False,
        alpha=1, verbose=False):
    if beam_search:
        sentences = []
        if lm_model.maintain_coverage:
            if lm_model.use_linguistic_coverage and lm_model.use_fertility_model:
                trans, aligns, costs, coverages, fertility = beam_search.search(seq, n_samples,
                        ignore_unk=ignore_unk, minlen=len(seq) / 2)
            else:
                trans, aligns, costs, coverages = beam_search.search(seq, n_samples,
                        ignore_unk=ignore_unk, minlen=len(seq) / 2)
        else:
            trans, aligns, costs = beam_search.search(seq, n_samples,
                    ignore_unk=ignore_unk, minlen=len(seq) / 2)
        if normalize:
            counts = [len(s) for s in trans]
            costs = [co / cn for co, cn in zip(costs, counts)]
        for i in range(len(trans)):
            sen = indices_to_words(lm_model.word_indxs, trans[i])
            sentences.append(" ".join(sen))
        for i in range(len(costs)):
            if verbose:
                print("{}: {}".format(costs[i], sentences[i]))
        if lm_model.maintain_coverage:
            if lm_model.use_linguistic_coverage and lm_model.use_fertility_model:
                return sentences, aligns, costs, coverages, fertility, trans
            else:
                return sentences, aligns, costs, coverages, trans
        else:
            return sentences, aligns, costs, trans
    elif sampler:
        sentences = []
        all_probs = []
        costs = []

        values, cond_probs = sampler(n_samples, 3 * (len(seq) - 1), alpha, seq)
        for sidx in range(n_samples):
            sen = []
            for k in range(values.shape[0]):
                if lm_model.word_indxs[values[k, sidx]] == '<eol>':
                    break
                sen.append(lm_model.word_indxs[values[k, sidx]])
            sentences.append(" ".join(sen))
            probs = cond_probs[:, sidx]
            probs = numpy.array(cond_probs[:len(sen) + 1, sidx])
            all_probs.append(numpy.exp(-probs))
            costs.append(-numpy.sum(probs))
        if normalize:
            counts = [len(s.strip().split(" ")) for s in sentences]
            costs = [co / cn for co, cn in zip(costs, counts)]
        sprobs = numpy.argsort(costs)
        if verbose:
            for pidx in sprobs:
                print("{}: {} {} {}".format(pidx, -costs[pidx], all_probs[pidx], sentences[pidx]))
            print()
        return sentences, costs, None
    else:
        raise Exception("I don't know what to do")


def parse_args():
    parser = argparse.ArgumentParser(
            "Sample (of find with beam-serch) translations from a translation model")
    parser.add_argument("--state",
            required=True, help="State to use")
    parser.add_argument("--beam-search",
            action="store_true", help="Beam size, turns on beam-search")
    parser.add_argument("--beam-size",
            type=int, help="Beam size")
    parser.add_argument("--ignore-unk",
            default=False, action="store_true",
            help="Ignore unknown words")
    parser.add_argument("--source",
            help="File of source sentences")
    parser.add_argument("--trans",
            help="File to save translations in")
    parser.add_argument("--normalize",
            action="store_true", default=False,
            help="Normalize log-prob with the word count")
    parser.add_argument("--verbose",
            action="store_true", default=False,
            help="Be verbose")
    parser.add_argument("model_path",
            help="Path to the model")
    parser.add_argument("changes",
            nargs="?", default="",
            help="Changes to state")
    return parser.parse_args()

def main():
    args = parse_args()

    state = prototype_search_with_coverage_state()
    with open(args.state) as src:
        state.update(pickle.load(src))
    state.update(eval("dict({})".format(args.changes)))

    logging.basicConfig(level=getattr(logging, state['level']), format="%(asctime)s: %(name)s: %(levelname)s: %(message)s")

    rng = numpy.random.RandomState(state['seed'])
    enc_dec = RNNEncoderDecoder(state, rng, skip_init=True, compute_alignment=True)
    enc_dec.build()
    lm_model = enc_dec.create_lm_model()
    lm_model.load(args.model_path)
    indx_word = pickle.load(open(state['word_indx'],'rb'))

    sampler = None
    beam_search = None
    if args.beam_search:
        beam_search = BeamSearch(enc_dec)
        beam_search.compile()
    else:
        sampler = enc_dec.create_sampler(many_samples=True)

    idict_src = pickle.load(open(state['indx_word'],'r'))

    if args.source and args.trans:
        # Actually only beam search is currently supported here
        assert beam_search
        assert args.beam_size

        fsrc = open(args.source, 'r')
        ftrans = open(args.trans, 'w')

        start_time = time.time()

        n_samples = args.beam_size
        total_cost = 0.0
        logging.debug("Beam size: {}".format(n_samples))
        for i, line in enumerate(fsrc):
            seqin = line.strip()
            seq, parsed_in = parse_input(state, indx_word, seqin, idx2word=idict_src)
            if lm_model.maintain_coverage:
                if lm_model.use_linguistic_coverage and lm_model.use_fertility_model:
                    trans, aligns, costs, coverages, fertility, _ = sample(lm_model, seq, n_samples, sampler=sampler,
                            beam_search=beam_search, ignore_unk=args.ignore_unk, normalize=args.normalize)
                else:
                    trans, aligns, costs, coverages, _ = sample(lm_model, seq, n_samples, sampler=sampler,
                            beam_search=beam_search, ignore_unk=args.ignore_unk, normalize=args.normalize)
            else:
                trans, aligns, costs, _ = sample(lm_model, seq, n_samples, sampler=sampler,
                        beam_search=beam_search, ignore_unk=args.ignore_unk, normalize=args.normalize)
            
            if args.verbose:
                print("Parsed Input:", parsed_in)

            if len(trans) == 0:
                trans = ['Failed']
                costs = [0.0]

            best = numpy.argmin(costs)
            print(trans[best], file=ftrans)
            if args.verbose:
                print("Translation:", trans[best])
                print("Aligns:")
                # aligns shape:  (target_len, source_len)
                # we reverse it to the shape (source_len, target_len) to show the matrix
                print(numpy.array(aligns[best]).transpose().tolist())

                if lm_model.maintain_coverage:
                    # since we filtered <eos> from trans[best], thus the index adds 1
                    coverage = coverages[best]
                    print("Coverage:", end=' ') 
                    words = parsed_in.split()
                    for k in range(len(words)):
                        print('%s/%.2f'%(words[k], coverage[k]), end=' ')
                    print('')
                    if lm_model.use_linguistic_coverage and lm_model.use_fertility_model:
                        print('Fertility:  ', end=' ')
                        for k in range(len(words)):
                            print('%s/%.2f'%(words[k], fertility[k]), end=' ')
                        print('')
                print() 

            total_cost += costs[best]
            if (i + 1)  % 100 == 0:
                ftrans.flush()
                logger.debug("Current speed is {} per sentence".
                        format((time.time() - start_time) / (i + 1)))
        print("Total cost of the translations: {}".format(total_cost))

        fsrc.close()
        ftrans.close()
    else:
        while True:
            try:
                seqin = input('Input Sequence: ')
                n_samples = int(input('How many samples? '))
                alpha = None
                if not args.beam_search:
                    alpha = float(input('Inverse Temperature? '))
                seq,parsed_in = parse_input(state, indx_word, seqin, idx2word=idict_src)
                print("Parsed Input:", parsed_in)
            except Exception:
                print("Exception while parsing your input:")
                traceback.print_exc()
                continue

            sample(lm_model, seq, n_samples, sampler=sampler,
                    beam_search=beam_search,
                    ignore_unk=args.ignore_unk, normalize=args.normalize,
                    alpha=alpha, verbose=True)

if __name__ == "__main__":
    main()
