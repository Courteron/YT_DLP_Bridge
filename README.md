Installation Guide
Install YT-DLP

Make sure Python and pip are installed, then run the following command:

<pre><code>pip install -U yt-dlp</code></pre>

This will install or update yt-dlp to the latest version.

Automatic startup configuration
Windows

To launch the program automatically at startup:

Press WIN + R

Type: shell:startup

Press Enter

Copy the file main.pyw into the folder that opens

Restart your computer, or log out and log back in

The script will now run automatically when Windows starts.

Linux / macOS / Other operating systems

Automatic startup depends on your operating system.

You need to place the main.pyw file in a location that runs at system startup.

Examples:

Linux:
~/.config/autostart/

macOS:
Use Login Items or LaunchAgents.

Refer to your operating system documentation for exact instructions.

Notes

main.pyw runs in the background without opening a console window

Make sure Python is installed and available in your system PATH

yt-dlp must be installed before running the script

Verify installation

You can verify that yt-dlp is installed correctly with:

yt-dlp --version

Requirements

Python 3.7 or newer

pip

Internet connection
