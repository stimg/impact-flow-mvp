LiveKit
--------

### Environment variables:
LIVEKIT_URL=wss://myrtc-0asan9q8.livekit.cloud
LIVEKIT_API_KEY=APIbJn9WLhRNhMr
LIVEKIT_API_SECRET=soTxPv0WvL9J9zaxJkwxY1PXV06rdjsTH0NUD7GSi4O

### Agent setup
```
# Init project:
uv init livekit-voice-agent --bare
cd livekit-voice-agent

# Add deps:
uv add \
"livekit-agents[silero,turn-detector]~=1.2" \
"livekit-plugins-noise-cancellation~=0.2" \
"python-dotenv"

# Add .env.local:
lk app env -w
```

Write the code
...

### Run locally
```
# Download deps:
uv run agent.py download-files

# Run in the console:
uv run agent.py console
```
### Connect to playground (LiveKit Cloud)
```
# Run in the debug mode:
uv run agent.py dev

# Run in the production mode:
uv run agent.py start
```

### Deploy to LiveKit Cloud
From the root of your project, run the following command with the LiveKit CLI. Ensure you have linked your LiveKit Cloud project and added the build and start scripts.
```
# Initial deplyment
lk agent create

# New version deployment
lk agent deploy
```

The CLI creates Dockerfile, .dockerignore, and livekit.toml files in your current directory, then registers your agent with your LiveKit Cloud project and deploys it.

After the deployment completes, you can access your agent in the playground, or continue to use the console mode as you build and test your agent locally.

### Monitor status and logs
Use the CLI to monitor the status and logs of your agent.
```
# Monitor agent status:
lk agent status

# Tail agent logs:
lk agent logs

```

### Rolling back
You can quickly rollback to a previous version of your agent, without a rebuild, by using the following command:
```
lk agent rollback
```

### Configuration with livekit.toml
The livekit.toml file contains your agent's deployment configuration. The CLI automatically looks for this file in the current directory, and uses it when any lk agent commands are run in that directory.
```
livekit.toml
[project]
subdomain = "<my-project-subdomain>"

[agent]
id = "<agent-id>"
```
To generate a new livekit.toml file, run:

```
lk agent config
```
JS SDK: https://github.com/livekit/client-sdk-js
LiveKit Cloud dashboard: https://cloud.livekit.io/
