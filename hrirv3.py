# -*- coding: utf-8 -*-

import os

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from autoeq.frequency_response import FrequencyResponse
from scipy import signal, fftpack

from constants import HEXADECAGONAL_TRACK_ORDER
from impulse_response import ImpulseResponse
from utils import read_wav, write_wav, magnitude_response, sync_axes


class HRIR:
    def __init__(self, estimator):
        self.estimator = estimator
        self.fs = self.estimator.fs
        self.irs_l = dict()
        self.irs_r = dict()

    def copy(self):
        hrir = HRIR(self.estimator)
        hrir.irs = dict()
        for speaker, pair in self.irs_l.items():
            hrir.irs_l[speaker] = {
                'left': pair['left'].copy(),
                'right': pair['right'].copy()
            }
        for speaker, pair in self.irs_r.items():
            hrir.irs_r[speaker] = {
                'left': pair['left'].copy(),
                'right': pair['right'].copy()
            }
        return hrir

    def open_recording(self, file_path, speaker, silence_length=1.0):
        if self.fs != self.estimator.fs:
            raise ValueError('Refusing to open recording because HRIR\'s sampling rate doesn\'t match impulse response '
                             'estimator\'s sampling rate.')

        fs, recording = read_wav(file_path, expand=True)
        if fs != self.fs:
            raise ValueError('Sampling rate of recording must match sampling rate of test signal.')

        if silence_length * self.fs != int(silence_length * self.fs):
            raise ValueError('Silence length must produce full samples with given sampling rate.')
        silence_length = int(silence_length * self.fs)

        # Crop out initial silence
        recording = recording[:, silence_length:]

        # Split sections in time to columns
        columns = []
        column_size = silence_length + len(self.estimator)
        for i in range(2):
            columns.append(recording[:, i * column_size:(i + 1) * column_size])

        if speaker not in self.irs_l:
            self.irs_l[speaker] = dict()
        if speaker not in self.irs_r:
            self.irs_r[speaker] = dict()
        self.irs_l[speaker]['left'] = ImpulseResponse(
            self.estimator.estimate(columns[0][0, :]),
            self.fs,
            columns[0][0, :]
        )
        self.irs_l[speaker]['right'] = ImpulseResponse(
            self.estimator.estimate(columns[0][1, :]),
            self.fs,
            columns[0][1, :]
        )
        self.irs_l[speaker]['refer'] = ImpulseResponse(
            self.estimator.estimate(columns[0][2, :]),
            self.fs,
            columns[0][2, :]
        )
        self.irs_r[speaker]['left'] = ImpulseResponse(
            self.estimator.estimate(columns[1][0, :]),
            self.fs,
            columns[1][0, :]
        )
        self.irs_r[speaker]['right'] = ImpulseResponse(
            self.estimator.estimate(columns[1][1, :]),
            self.fs,
            columns[1][1, :]
        )
        self.irs_r[speaker]['refer'] = ImpulseResponse(
            self.estimator.estimate(columns[1][2, :]),
            self.fs,
            columns[1][2, :]
        )

    def write_wav(self, file_path, track_order=None, bit_depth=32):
        """Writes impulse responses to a WAV file

        Args:
            file_path: Path to output WAV file
            track_order: List of speaker-side names for the order of impulse responses in the output file
            bit_depth: Number of bits per sample. 16, 24 or 32

        Returns:
            None
        """
        # Duplicate speaker names as left and right side impulse response names
        if track_order is None:
            track_order = HEXADECAGONAL_TRACK_ORDER

        # Add all impulse responses to a list and save channel names
        irs = []
        ir_order = []
        for speaker, pair in self.irs.items():
            for side, ir in pair.items():
                irs.append(ir.data)
                ir_order.append(f'{speaker}-{side}')

        # Add silent tracks
        for ch in track_order:
            if ch not in ir_order:
                irs.append(np.zeros(len(irs[0])))
                ir_order.append(ch)
        irs = np.vstack(irs)

        # Sort to output order
        irs = irs[[ir_order.index(ch) for ch in track_order], :]

        # Write to file
        write_wav(file_path, self.fs, irs, bit_depth=bit_depth)

    def write_wav_list(self, file_path, bit_depth=32):
        # Add all impulse responses to a list and save channel names
        for speaker, pair in self.irs_l.items():
            irs = []
            for side, ir in pair.items():
                irs.append(ir.data)
            irs = np.vstack(irs)
            write_wav(os.path.join(file_path, "L", speaker + ".wav"), self.fs, irs, bit_depth=bit_depth)
        for speaker, pair in self.irs_r.items():
            irs = []
            for side, ir in pair.items():
                irs.append(ir.data)
            irs = np.vstack(irs)
            write_wav(os.path.join(file_path, "R", speaker + ".wav"), self.fs, irs, bit_depth=bit_depth)

    def normalize(self, peak_target=-0.1, avg_target=None):
        """Normalizes output gain to target.

        Args:
            peak_target: Target gain of the peak in dB
            avg_target: Target gain of the mid frequencies average in dB

        Returns:
            None
        """
        # Stack and sum all left and right ear impulse responses separately
        left = []
        right = []
        for speaker, pair in self.irs.items():
            left.append(pair['left'].data)
            right.append(pair['right'].data)
        left = np.sum(np.vstack(left), axis=0)
        right = np.sum(np.vstack(right), axis=0)

        # Calculate magnitude responses
        f_l, mr_l = magnitude_response(left, self.fs)
        f_r, mr_r = magnitude_response(right, self.fs)

        if peak_target is not None and avg_target is None:
            # Maximum absolute gain from both sides
            gain = np.max(np.vstack([mr_l, mr_r])) * -1 + peak_target

        elif peak_target is None and avg_target is not None:
            # Mid frequencies average from both sides
            gain = np.mean(np.concatenate([
                mr_l[np.logical_and(f_l > 80, f_l < 6000)],
                mr_r[np.logical_and(f_r > 80, f_r < 6000)]
            ]))
            gain = gain * -1 + avg_target

        else:
            raise ValueError('One and only one of the parameters "peak_target" and "avg_target" must be given!')

        gain /= len(self.irs.items()) / 2

        # Scale impulse responses
        for speaker, pair in self.irs.items():
            for ir in pair.values():
                ir.data *= 10 ** (gain / 20)

    def crop_heads_for_each(self, irs):
        for speaker, pair in irs.items():
            peak_refer = pair['refer'].peak_index()
            pair['left'].data = pair['left'].data[peak_refer:]
            pair['right'].data = pair['right'].data[peak_refer:]

    def crop_heads(self):
        """Crops heads of impulse responses

        Returns:
            None
        """
        if self.fs != self.estimator.fs:
            raise ValueError('Refusing to crop heads because HRIR sampling rate doesn\'t match impulse response '
                             'estimator\'s sampling rate.')
        self.crop_heads_for_each(self.irs_l)
        self.crop_heads_for_each(self.irs_r)

    def crop_tails_for_each(self, irs):
        tail_indices = []
        lengths = []
        for speaker, pair in irs.items():
            for side, ir in pair.items():
                _, tail_ind, _, _ = ir.decay_params()
                tail_indices.append(tail_ind)
                lengths.append(len(ir))

        # Crop all tracks by last tail index
        seconds_per_octave = len(self.estimator) / self.estimator.fs / self.estimator.n_octaves
        fade_out = 2 * int(self.fs * seconds_per_octave * (1 / 24))  # Duration of 1/24 octave in the sweep
        window = signal.hanning(fade_out)[fade_out // 2:]
        fft_len = fftpack.next_fast_len(max(tail_indices))
        tail_ind = min(np.min(lengths), fft_len)
        for speaker, pair in irs.items():
            for ir in pair.values():
                ir.data = ir.data[:tail_ind]
                ir.data *= np.concatenate([np.ones(len(ir.data) - len(window)), window])

    def crop_tails(self):
        """Crops out tails after every impulse response has decayed to noise floor."""
        if self.fs != self.estimator.fs:
            raise ValueError('Refusing to crop tails because HRIR\'s sampling rate doesn\'t match impulse response '
                             'estimator\'s sampling rate.')
        # Find indices after which there is only noise in each track
        self.crop_tails_for_each(self.irs_l)
        self.crop_tails_for_each(self.irs_r)

    def channel_balance_firs(self, left_fr, right_fr, method):
        """Creates FIR filters for correcting channel balance

        Args:
            left_fr: Left side FrequencyResponse instance
            right_fr: Right side FrequencyResponse instance
            method: "trend" equalizes right side by the difference trend of right and left side. "left" equalizes
                    right side to left side fr, "right" equalizes left side to right side fr, "avg" equalizes both
                    to the average fr, "min" equalizes both to the minimum of left and right side frs. Number
                    values will boost or attenuate right side relative to left side by the number of dBs. "mids" is
                    the same as the numerical values but guesses the value automatically from mid frequency levels.

        Returns:
            List of two FIR filters as numpy arrays, first for left and second for right
        """
        if method == 'mids':
            # Find gain for right side
            # R diff - L diff = L mean - R mean
            gain = right_fr.copy().center([100, 3000]) - left_fr.copy().center([100, 3000])
            gain = 10 ** (gain / 20)
            n = int(round(self.fs * 0.1))  # 100 ms
            firs = [signal.unit_impulse(n), signal.unit_impulse(n) * gain]

        elif method == 'trend':
            trend = FrequencyResponse(name='trend', frequency=left_fr.frequency, raw=left_fr.raw - right_fr.raw)
            trend.smoothen_fractional_octave(
                window_size=2,
                treble_f_lower=20000,
                treble_f_upper=int(round(self.fs / 2))
            )
            # Trend is the equalization target
            right_fr.equalization = trend.smoothed
            # Unit impulse for left side and equalization FIR filter for right side
            fir = right_fr.minimum_phase_impulse_response(fs=self.fs, normalize=False)
            firs = [signal.unit_impulse((len(fir))), fir]

        elif method == 'left' or method == 'right':
            if method == 'left':
                ref = left_fr
                subj = right_fr
            else:
                ref = right_fr
                subj = left_fr

            # Smoothen reference
            ref.smoothen_fractional_octave(
                window_size=1 / 3,
                treble_f_lower=20000,
                treble_f_upper=int(round(self.fs / 2))
            )
            # Center around 0 dB
            gain = ref.center([100, 10000])
            subj.raw += gain
            # Compensate and equalize to reference
            subj.target = ref.smoothed
            subj.error = subj.raw - subj.target
            subj.smoothen_heavy_light()
            subj.equalize(max_gain=15, treble_f_lower=20000, treble_f_upper=self.fs / 2)
            # Unit impulse for left side and equalization FIR filter for right side
            fir = subj.minimum_phase_impulse_response(fs=self.fs, normalize=False)
            if method == 'left':
                firs = [signal.unit_impulse((len(fir))), fir]
            else:
                firs = [fir, signal.unit_impulse((len(fir)))]

        elif method == 'avg' or method == 'min':
            # Center around 0 dB
            left_gain = left_fr.copy().center([100, 10000])
            right_gain = right_fr.copy().center([100, 10000])
            gain = (left_gain + right_gain) / 2
            left_fr.raw += gain
            right_fr.raw += gain

            # Smoothen
            left_fr.smoothen_fractional_octave(window_size=1 / 3, treble_f_lower=20000, treble_f_upper=23999)
            right_fr.smoothen_fractional_octave(window_size=1 / 3, treble_f_lower=20000, treble_f_upper=23999)

            # Target
            if method == 'avg':
                # Target is the average between the two FRs
                target = (left_fr.raw + right_fr.raw) / 2
            else:
                # Target is the  frequency-vise minimum of the two FRs
                target = np.min([left_fr.raw, right_fr.raw], axis=0)

            # Compensate and equalize both to the target
            firs = []
            for fr in [left_fr, right_fr]:
                fr.target = target.copy()
                fr.error = fr.raw - fr.target
                fr.smoothen_fractional_octave(window_size=1 / 3, treble_f_lower=20000, treble_f_upper=23999)
                fr.equalize(max_gain=15, treble_f_lower=2000, treble_f_upper=self.fs / 2)
                firs.append(fr.minimum_phase_impulse_response(fs=self.fs, normalize=False))

        else:
            # Must be numerical value
            try:
                gain = 10 ** (float(method) / 20)
                n = int(round(self.fs * 0.1))  # 100 ms
                firs = [signal.unit_impulse(n), signal.unit_impulse(n) * gain]
            except ValueError:
                raise ValueError(f'"{method}" is not valid value for channel balance method.')

        return firs

    def correct_channel_balance(self, method):
        """Channel balance correction by equalizing left and right ear results to the same frequency response.

           Args:
               method: "trend" equalizes right side by the difference trend of right and left side. "left" equalizes
                       right side to left side fr, "right" equalizes left side to right side fr, "avg" equalizes both
                       to the average fr, "min" equalizes both to the minimum of left and right side frs. Number
                       values will boost or attenuate right side relative to left side by the number of dBs. "mids" is
                       the same as the numerical values but guesses the value automatically from mid frequency levels.

           Returns:
               HRIR with FIR filter for equalizing each speaker-side
           """
        # Create frequency responses for left and right side IRs
        stacks = [[], []]
        for speaker, pair in self.irs.items():
            if speaker not in ['FL', 'FR']:
                continue
            for i, ir in enumerate(pair.values()):
                stacks[i].append(ir.data)

        # Group the same left and right side speakers
        eqir = HRIR(self.estimator)
        for speakers in [['FC'], ['FL', 'FR'], ['SL', 'SR'], ['BL', 'BR']]:
            if len([ch for ch in speakers if ch in self.irs]) < len(speakers):
                # All the speakers in the current speaker group must exist, otherwise balancing makes no sense
                continue
            # Stack impulse responses
            left, right = [], []
            for speaker in speakers:
                left.append(self.irs[speaker]['left'].data)
                right.append(self.irs[speaker]['right'].data)
            # Create frequency responses
            left_fr = ImpulseResponse(np.mean(np.vstack(left), axis=0), self.fs).frequency_response()
            right_fr = ImpulseResponse(np.mean(np.vstack(right), axis=0), self.fs).frequency_response()
            # Create EQ FIR filters
            firs = self.channel_balance_firs(left_fr, right_fr, method)
            # Assign to speakers in EQ HRIR
            for speaker in speakers:
                self.irs[speaker]['left'].equalize(firs[0])
                self.irs[speaker]['right'].equalize(firs[1])

        return eqir

    def plot_result_each(self, irs, dir_path):
        """Plot left and right side results with all impulse responses stacked

        Args:
            dir_path: Path to directory for saving the figure

        Returns:
            None
        """
        stacks = [[], []]
        for speaker, pair in irs.items():
            for i, ir in enumerate(pair.values()):
                stacks[i].append(ir.data)
        left = ImpulseResponse(np.sum(np.vstack(stacks[0]), axis=0), self.fs)
        left_fr = left.frequency_response()
        left_fr.smoothen_fractional_octave(window_size=1 / 3, treble_f_lower=20000, treble_f_upper=23999)
        right = ImpulseResponse(np.sum(np.vstack(stacks[1]), axis=0), self.fs)
        right_fr = right.frequency_response()
        right_fr.smoothen_fractional_octave(window_size=1 / 3, treble_f_lower=20000, treble_f_upper=23999)

        fig, ax = plt.subplots()
        fig.set_size_inches(60, 45)
        left.plot_fr(fig=fig, ax=ax, fr=left_fr, plot_raw=True, raw_color='#7db4db', plot_smoothed=False)
        right.plot_fr(fig=fig, ax=ax, fr=right_fr, plot_raw=True, raw_color='#dd8081', plot_smoothed=False)
        left.plot_fr(fig=fig, ax=ax, fr=left_fr, plot_smoothed=True, smoothed_color='#1f77b4', plot_raw=False)
        right.plot_fr(fig=fig, ax=ax, fr=right_fr, plot_smoothed=True, smoothed_color='#d62728', plot_raw=False)
        ax.plot(left_fr.frequency, left_fr.smoothed - right_fr.smoothed, color='#680fb9')
        ax.legend(['Left raw', 'Right raw', 'Left smoothed', 'Right smoothed', 'Difference'])

        # Save figures
        file_path = os.path.join(dir_path, f'results.png')
        fig.savefig(file_path, bbox_inches='tight')
        plt.close(fig)
        # Optimize file size
        im = Image.open(file_path)
        im = im.convert('P', palette=Image.ADAPTIVE, colors=60)
        im.save(file_path, optimize=True)

    def plot_result(self, dir_path):
        self.plot_result_each(self.irs_l, dir_path)
        self.plot_result_each(self.irs_r, dir_path)

    def equalize(self, fir):
        """Equalizes all impulse responses with given FIR filters.

        First row of the fir matrix will be used for all left side impulse responses and the second row for all right
        side impulse responses.

        Args:
            fir: FIR filter as an array like. Must have same sample rate as this HRIR instance.

        Returns:
            None
        """
        if type(fir) == list:
            # Turn list (list|array|ImpulseResponse) into Numpy array
            if type(fir[0]) == np.ndarray:
                fir = np.vstack(fir)
            elif type(fir[0]) == list:
                fir = np.array(fir)
            elif type(fir[0]) == ImpulseResponse:
                if len(fir) > 1:
                    fir = np.vstack([fir[0].data, fir[1].data])
                else:
                    fir = fir[0].data.copy()

        if len(fir.shape) == 1 or fir.shape[0] == 1:
            # Single track in the WAV file, use it for both channels
            fir = np.tile(fir, (2, 1))

        for speaker, pair in self.irs.items():
            for side, ir in pair.items():
                ir.equalize(fir[0] if side == 'left' else fir[1])

    def resample(self, fs):
        """Resamples all impulse response to the given sampling rate.

        Sets internal sampling rate to the new rate. This will disable file reading and cropping so this should be
        the last method called in the processing pipeline.

        Args:
            fs: New sampling rate in Hertz

        Returns:
            None
        """
        for speaker, pair in self.irs.items():
            for side, ir in pair.items():
                ir.resample(fs)
        self.fs = fs
