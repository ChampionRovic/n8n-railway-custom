# Start from official n8n image
FROM n8nio/n8n:latest

# Install your community nodes
RUN npm install n8n-nodes-openai n8n-nodes-notion-extended n8n-nodes-google n8n-nodes-slack-extended

# Expose n8n port
EXPOSE 5678

# Start n8n
CMD ["n8n", "start"]
