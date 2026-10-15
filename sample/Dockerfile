FROM golang:1.27.2-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
ARG REVISION=v1
ARG MODE=healthy
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-X main.revision=${REVISION} -X main.defaultMode=${MODE}" -o /out/sample .
FROM alpine:3.23
RUN adduser -D -u 10001 app
COPY --from=build /out/sample /usr/local/bin/sample
USER app
ENTRYPOINT ["sample"]
