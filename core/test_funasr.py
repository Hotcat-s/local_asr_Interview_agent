from funasr import AutoModel


# Chinese production (VAD + ASR + punctuation + speaker)
# model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc", spk_model="cam++", device="cuda",model_path="")
model = AutoModel(
    model="/home/qiuqiu/local_Interview_agent/core/models/Paraformer-zh/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    vad_model="/home/qiuqiu/local_Interview_agent/core/models/fsmn-vad/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    punc_model="/home/qiuqiu/local_Interview_agent/core/models/ct-punc/punc_ct-transformer_cn-en-common-vocab471067-large",
    spk_model="/home/qiuqiu/local_Interview_agent/core/models/cam++/speech_campplus_sv_zh-cn_16k-common",
    device="cuda",
)
result = model.generate(input="https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav", hotword="关键词 20")
print(result)

# # Streaming real-time (feed audio chunk by chunk)
# import soundfile as sf
# model = AutoModel(model="paraformer-zh-streaming", device="cuda")
# audio, sr = sf.read("speech.wav", dtype="float32")   # 16 kHz mono
# chunk_size = [0, 10, 5]                               # 600 ms chunks
# chunk_stride = chunk_size[1] * 960
# cache = {}
# n_chunks = (len(audio) - 1) // chunk_stride + 1
# for i in range(n_chunks):
#     chunk = audio[i * chunk_stride : (i + 1) * chunk_stride]
#     res = model.generate(input=chunk, cache=cache, is_final=(i == n_chunks - 1),
#                          chunk_size=chunk_size, encoder_chunk_look_back=4, decoder_chunk_look_back=1)
#     if res[0]["text"]:
#         print(res[0]["text"], end="", flush=True)

# # Emotion recognition
# model = AutoModel(model="emotion2vec_plus_large", device="cuda")
# result = model.generate(input="audio.wav", granularity="utterance")