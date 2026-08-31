FROM node:20-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install --production

# Copy bridge source
COPY . .

EXPOSE 3000

CMD ["node", "index.js"]
