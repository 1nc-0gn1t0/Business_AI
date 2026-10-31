FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY tools/patch-redocly-minimatch.cjs ./tools/
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951
# Remove unused curl CLI and its automatically installed dependency closure.
RUN apk del --no-network curl
# Alpine3.24 security patch; signature + checksum verified, no floating upgrade.
ADD --checksum=sha256:62a7e37e43bbfc1f8525a00ad2125fd5897135dc93b849733884cb78ffd8e26c https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/brotli-libs-1.2.1-r0.apk /tmp/brotli-libs.apk
RUN apk add --no-network /tmp/brotli-libs.apk && rm /tmp/brotli-libs.apk
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
