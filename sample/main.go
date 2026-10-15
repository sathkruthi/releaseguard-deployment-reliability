package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

var revision = "v1"
var defaultMode = "healthy"
var buckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5}

type metrics struct {
	sync.Mutex
	outcomes map[string]int
	counts   []int
	total    int
	seconds  float64
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	role := os.Getenv("ROLE")
	if role == "" {
		role = "app"
	}
	m := metrics{outcomes: map[string]int{"success": 0, "revision": 0, "dependency": 0}, counts: make([]int, len(buckets))}
	client := &http.Client{Timeout: 500 * time.Millisecond}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /live", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("live\n")) })
	mux.HandleFunc("GET /ready", func(w http.ResponseWriter, r *http.Request) {
		if role == "app" && defaultMode == "broken" {
			http.Error(w, "revision readiness failure", 503)
			return
		}
		w.Write([]byte("ready\n"))
	})
	mux.HandleFunc("GET /check", func(w http.ResponseWriter, r *http.Request) {
		if role != "dependency" {
			http.NotFound(w, r)
			return
		}
		if os.Getenv("DEPENDENCY_FAIL") == "1" {
			http.Error(w, "synthetic dependency outage", 503)
			return
		}
		w.Write([]byte("dependency healthy\n"))
	})
	mux.HandleFunc("GET /work", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		outcome := "success"
		status := 200
		if defaultMode == "broken" {
			outcome = "revision"
			status = 503
		} else {
			if defaultMode == "slow" {
				time.Sleep(700 * time.Millisecond)
			}
			url := os.Getenv("DEPENDENCY_URL")
			if url == "" {
				url = "http://releaseguard-dependency:8080/check"
			}
			response, err := client.Get(url)
			if err != nil {
				outcome = "dependency"
				status = 503
			} else {
				response.Body.Close()
				if response.StatusCode != 200 {
					outcome = "dependency"
					status = 503
				}
			}
		}
		seconds := time.Since(start).Seconds()
		m.Lock()
		m.outcomes[outcome]++
		m.total++
		m.seconds += seconds
		for i, b := range buckets {
			if seconds <= b {
				m.counts[i]++
			}
		}
		m.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		fmt.Fprintf(w, "{\"revision\":%q,\"outcome\":%q}\n", revision, outcome)
		log.Info("request completed", "revision", revision, "outcome", outcome, "seconds", seconds)
	})
	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		ready := 1
		if defaultMode == "broken" {
			ready = 0
		}
		fmt.Fprintf(w, "releaseguard_app_ready{revision=%q} %d\n", revision, ready)
		m.Lock()
		defer m.Unlock()
		for _, outcome := range []string{"success", "revision", "dependency"} {
			fmt.Fprintf(w, "releaseguard_requests_total{revision=%q,outcome=%q} %d\n", revision, outcome, m.outcomes[outcome])
		}
		for i, b := range buckets {
			fmt.Fprintf(w, "releaseguard_request_seconds_bucket{revision=%q,le=%q} %d\n", revision, fmt.Sprint(b), m.counts[i])
		}
		fmt.Fprintf(w, "releaseguard_request_seconds_bucket{revision=%q,le=\"+Inf\"} %d\nreleaseguard_request_seconds_count{revision=%q} %d\nreleaseguard_request_seconds_sum{revision=%q} %g\n", revision, m.total, revision, m.total, revision, m.seconds)
	})
	server := &http.Server{Addr: ":8080", Handler: mux, ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 3 * time.Second, WriteTimeout: 3 * time.Second, IdleTimeout: 10 * time.Second}
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	go func() {
		<-ctx.Done()
		end, done := context.WithTimeout(context.Background(), 3*time.Second)
		defer done()
		server.Shutdown(end)
	}()
	log.Info("sample started", "revision", revision, "mode", defaultMode, "role", role)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Error("server failed")
		os.Exit(1)
	}
}
