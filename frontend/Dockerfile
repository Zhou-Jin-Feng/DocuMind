ARG NODE_BASE_IMAGE=node:22-alpine
FROM ${NODE_BASE_IMAGE}

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://127.0.0.1:8001
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
