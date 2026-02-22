FROM node:20-alpine

WORKDIR /app/apps/web

COPY apps/web/package.json ./package.json
RUN npm install

COPY apps/web .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
