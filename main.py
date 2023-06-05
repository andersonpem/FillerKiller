#!/usr/bin/env python3
import argparse
import os
import subprocess
import wave
import json
from vosk import Model, KaldiRecognizer
from moviepy.editor import VideoFileClip, concatenate

script_dir = os.path.dirname(os.path.realpath(__file__))


def transcribe_video(video_path, modelPath):
    model = Model(modelPath)
    # Open the video file and extract the audio
    audio_path = "temp.wav"
    command = f"ffmpeg -i {video_path} -vn -acodec pcm_s16le -ar 16000 -ac 1 {audio_path}"
    subprocess.call(command, shell=True)

    # Open the audio file
    wf = wave.open(audio_path, "rb")

    # Initialize the recognizer
    recognizer = KaldiRecognizer(model, wf.getframerate())

    # Process the audio file in chunks
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        recognizer.AcceptWaveform(data)

    # Get the final transcription result as a JSON string
    result = recognizer.FinalResult()

    # Parse the JSON string to extract the transcribed text
    words = json.loads(result)["result"]

    # Create a list to hold the word-by-word timestamps
    word_timestamps = []

    # Iterate through each word in the result
    for word in words:
        start_time = word["start"]
        end_time = word["end"]
        word_text = word["word"]
        word_timestamps.append({"start": start_time, "end": end_time, "word": word_text})

    # Close the audio file and delete the temporary file
    wf.close()
    os.remove(audio_path)

    if json_print is True:
        with open('transcription.json', 'w') as file:
            file.write(json.dumps(word_timestamps, indent=1))
    # Return the word-by-word timestamps as JSON
    return json.dumps(word_timestamps)


def remove_fillers(video_path, threshold, modelPath, video_codec="h264_nvenc", bitrate="5M"):
    # Specify the file paths of the undesired words
    normal_fillers_file = script_dir + '/fillers_normal.txt'
    threshold_fillers_file = script_dir + '/fillers_threshold.txt'

    file_paths = [normal_fillers_file, threshold_fillers_file]

    for file_path in file_paths:
        if not os.path.exists(file_path):
            print('One of the fillers file is not present in the repository folder! Please check it and run again.')
            exit(1)

    # Transcribe the video and get the word-by-word timestamps
    timestamps_json = transcribe_video(video_path, modelPath)

    # Parse the JSON to obtain the word-by-word timestamps
    word_timestamps = json.loads(timestamps_json)

    # Read the normal fillers from the file into a list
    with open(normal_fillers_file, 'r') as file:
        normal_fillers = [line.strip() for line in file]

    # Read the threshold fillers from the file into a list
    with open(threshold_fillers_file, 'r') as file:
        threshold_fillers = [line.strip() for line in file]

    # Find the timestamps of the normal fillers and threshold fillers
    filler_timestamps = []
    previous_end = 0
    for i, word in enumerate(word_timestamps):
        word_text = word["word"]
        start_time = word["start"]
        end_time = word["end"]

        if word_text in normal_fillers:
            filler_timestamps.append((start_time, end_time))
        elif word_text in threshold_fillers:
            # Check if the word duration exceeds the threshold or has a large gap to the next word
            next_word = word_timestamps[i + 1] if i < len(word_timestamps) - 1 else None
            next_start_time = next_word["start"] if next_word else end_time
            if end_time - start_time > threshold or next_start_time - end_time > threshold:
                filler_timestamps.append((start_time, end_time))

    # Construct the command to concatenate the video segments using FFmpeg
    segments = []
    previous_end = 0
    for start, end in filler_timestamps:
        start_time = start
        end_time = end
        segment_path = f"segment_{start_time}_{end_time}.mkv"
        segments.append(segment_path)
        command = f'ffmpeg -i {video_path} -ss {previous_end} -to {start_time} -c:v {video_codec} -b:v {bitrate} -c:a copy {segment_path}'
        subprocess.call(command, shell=True)
        previous_end = end_time

    # Concatenate the segments to create the edited video
    concat_list_path = "concat_list.txt"
    with open(concat_list_path, 'w') as file:
        for segment_path in segments:
            file.write(f"file '{segment_path}'\n")

    edited_video_path = os.path.splitext(video_path)[0] + '_no_fillers.mkv'
    command = f'ffmpeg -f concat -safe 0 -i {concat_list_path} -c:v {video_codec} -b:v {bitrate} -c:a aac {edited_video_path}'
    subprocess.call(command, shell=True)

    # Clean up temporary files
    for segment_path in segments:
        os.remove(segment_path)
    os.remove(concat_list_path)

    print("Edited Video:", edited_video_path)


if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="Remove filler words from a video using a local Vosk model. You must"
                                                 "have the files normal_fillers.txt and threshold_fillers.txt set.")
    parser.add_argument("--file", type=str, required=True, help="Path to the video file to remove filler words")
    parser.add_argument("--threshold", type=float, default=0.5, help="Special words minimum threshold for slicing.")
    parser.add_argument("--model", type=str, required=False, help="Path to the vosk model used")
    parser.add_argument("--json", type=bool, required=False, help="Prints the Vosk content to a json file.")
    parser.add_argument("--bitrate", type=str, default="6M", help="Bitrate for video encoding (e.g., '5M' for 5 Mbps)")
    # Parse the arguments
    args = parser.parse_args()
    bitrate = args.bitrate
    if args.json is not None and args.model != "":
        json_print = True
        print("JSON transcription will be written in transcription.json =)")
    else:
        json_print = False
    if os.path.exists(script_dir + '/vosk_model.txt'):
        print("Vosk model path is being read from vosk_model.txt")
        with open(script_dir + '/vosk_model.txt', 'r') as file:
            path_with_env = file.readline().strip()
            vosk_path = os.path.expandvars(path_with_env)
    else:
        if args.model is not None and args.model != "":
            vosk_path = args.model
        else:
            print("You must specify a model if your model is not set in vosk_model.txt")
            exit(1)

    # Call the process_file function with the provided arguments
    remove_fillers(args.file, args.threshold, vosk_path, bitrate=bitrate)
