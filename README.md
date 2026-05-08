# AudioMancer

AudioMancer is a Windows desktop app for book translation and audiobook preparation.

It can help you:

- import a book and extract the text
- clean and split long text into workable pieces
- translate a book into another language
- find characters and prepare narrator or character voices
- create speech blocks for audiobook production
- generate local voice audio through VoiceWeaver
- assemble final WAV audiobook files

AI help is optional. You can use AI for cleanup, chunking, translation, character discovery, and speech blocks, then review and edit the result. You can also do the same work manually.

## Windows Downloads

AudioMancer is currently tested on Windows.

Download from the current GitHub Release:

- [AudioMancer_Windows_x64.zip](https://github.com/DDP-Engineering/2026_AudioMancer/releases/latest/download/AudioMancer_Windows_x64.zip)
- [SHA256SUMS.txt](https://github.com/DDP-Engineering/2026_AudioMancer/releases/latest/download/SHA256SUMS.txt)
- every `VoiceWeaver*.zip.partNNN` file listed in the same release

VoiceWeaver is split into numbered release assets because the full Windows package can be larger than one GitHub release asset. The number of parts can change from one release to another. Always download all matching parts from the same release.

## Install AudioMancer

1. Download `AudioMancer_Windows_x64.zip`.
2. Extract it to a normal folder, for example `C:\AudioMancer`.
3. Start AudioMancer with `AudioMancer.exe` or `Start-AudioMancer.cmd`.

## Install VoiceWeaver

1. Download all matching VoiceWeaver `.partNNN` files from the same release.
2. Put all parts in one folder.
3. Reassemble the VoiceWeaver ZIP with PowerShell.
4. Extract the VoiceWeaver ZIP to a normal folder, for example `C:\VoiceWeaver`.
5. Start VoiceWeaver with its Windows start file.
6. Check that the local health address works: `http://127.0.0.1:8059/v1/health`.

## Reassemble VoiceWeaver On Windows

Run this from the folder containing all VoiceWeaver parts:

```powershell
$outputZip = "VoiceWeaver-v1.2.2-windows-x64-cuda-models-2.zip"
$parts = Get-ChildItem "$outputZip.part*" | Sort-Object Name
$out = [IO.File]::Create($outputZip)
foreach ($part in $parts) {
    $in = [IO.File]::OpenRead($part.FullName)
    $in.CopyTo($out)
    $in.Dispose()
}
$out.Dispose()
Get-FileHash -Algorithm SHA256 $outputZip
```

If a future release uses a different VoiceWeaver ZIP name, set `$outputZip` to that release's ZIP name before running the command.

## Current VoiceWeaver Package

The current VoiceWeaver package contains:

- `Qwen3-TTS-12Hz-1.7B-Base`
- `Qwen3-TTS-12Hz-1.7B-VoiceDesign`

Expected reassembled VoiceWeaver ZIP SHA256:

```text
a7ebe2dd594586da8b321aedd41ea8ddd12a4ee68a353c1e48b8dd6c5ee3aa5a
```

Expected AudioMancer ZIP SHA256:

```text
3ada57acf69d22bf9c707645945cef6d716c880f9213eda652e2da3db926ff3f
```

Use `SHA256SUMS.txt` for the complete list of hashes, including every VoiceWeaver part.

## Connect AudioMancer To VoiceWeaver

1. Start VoiceWeaver first.
2. Start AudioMancer.
3. Open `TTS Settings`.
4. Set `Base URL` to `http://127.0.0.1:8059`.
5. Leave `API Key` empty for normal local use.
6. Press `Test Connection`.
7. Save the TTS settings.

## AI Setup

AudioMancer can use local AI models or online OpenAI-compatible models.

For local AI with LM Studio:

1. Start the LM Studio local server.
2. In AudioMancer, open `AI Settings`.
3. Set `Backend Kind` to `lmstudio`.
4. Set `Base URL` to `http://localhost:1234/v1`.
5. Set `Model Name` to the model name shown by LM Studio.
6. Save the profile and select it as the default for the workflow steps you want to run locally.

For online AI:

1. In AudioMancer, open `AI Settings`.
2. Set `Backend Kind` to `openai_compatible`.
3. Set the provider base URL, for example `https://api.openai.com/v1`.
4. Add your API key.
5. Set the model name and save the profile.

## Distribution Scope

This public repository is used for executable release delivery and the download webpage. It does not host the application source code.

## License

AudioMancer and VoiceWeaver are distributed under the license files included in each release archive.
