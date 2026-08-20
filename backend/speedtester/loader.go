package speedtester

import (
	"encoding/base64"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"

	"github.com/metacubex/mihomo/adapter"
	"github.com/metacubex/mihomo/adapter/provider"
	"github.com/metacubex/mihomo/common/convert"
	"github.com/metacubex/mihomo/constant"
	"github.com/zhsama/clash-speedtest/logger"
	"gopkg.in/yaml.v3"
)

// RawConfig raw configuration structure for parsing
type RawConfig struct {
	Providers map[string]map[string]any `yaml:"proxy-providers"`
	Proxies   []map[string]any          `yaml:"proxies"`
}

// LoadProxies loads and filters proxies from configuration paths
func (st *SpeedTester) LoadProxies(stashCompatible bool) (map[string]*CProxy, error) {
	logger.Logger.Info("Starting proxy loading",
		slog.String("config_paths", st.config.ConfigPaths),
		slog.Bool("stash_compatible", stashCompatible),
	)

	allProxies := make(map[string]*CProxy)
	configPaths := strings.Split(st.config.ConfigPaths, ",")

	for i, configPath := range configPaths {
		// Trim spaces and remove quotes
		configPath = strings.TrimSpace(configPath)
		if (strings.HasPrefix(configPath, "\"") && strings.HasSuffix(configPath, "\"")) ||
			(strings.HasPrefix(configPath, "'") && strings.HasSuffix(configPath, "'")) {
			configPath = configPath[1 : len(configPath)-1]
		}

		if configPath == "" {
			continue
		}

		logger.Logger.Info("Loading config from path",
			slog.String("path", configPath),
			slog.Int("index", i),
		)

		var body []byte
		var err error
		if strings.HasPrefix(configPath, "http") {
			var resp *http.Response
			resp, err = http.Get(configPath)
			if err != nil {
				logger.LogError("Failed to fetch config", err, slog.String("url", configPath))
				continue
			}
			defer resp.Body.Close()

			body, err = io.ReadAll(resp.Body)
		} else {
			body, err = os.ReadFile(configPath)
		}
		if err != nil {
			logger.LogError("Failed to read config", err, slog.String("path", configPath))
			continue
		}

		// Try to detect and decode base64 encoded configuration
		if strings.TrimSpace(string(body)) != "" {
			if decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(string(body))); err == nil {
				// Check if decoded content is valid YAML
				if strings.Contains(string(decoded), "proxies:") || strings.Contains(string(decoded), "proxy-providers:") {
					body = decoded
					logger.Logger.Debug("Successfully decoded base64 config", slog.String("path", configPath))
				}
			}
		}

		rawCfg := &RawConfig{
			Proxies: []map[string]any{},
		}
		if err := yaml.Unmarshal(body, rawCfg); err != nil {
			// Some subscriptions return a base64-encoded list of share-link URIs
			// (one per line) instead of a YAML config. Fall back to URI parsing.
			proxies, uriErr := parseURISubscription(body)
			if uriErr != nil {
				logger.LogError("Failed to parse config", err, slog.String("path", configPath))
				return nil, err
			}
			rawCfg.Proxies = proxies
			logger.Logger.Debug("Parsed proxy URI subscription",
				slog.String("path", configPath),
				slog.Int("proxy_count", len(proxies)),
			)
		}

		logger.Logger.Info("Config parsed successfully",
			slog.String("path", configPath),
			slog.Int("proxy_count", len(rawCfg.Proxies)),
			slog.Int("provider_count", len(rawCfg.Providers)),
		)

		proxies := make(map[string]*CProxy)
		proxiesConfig := rawCfg.Proxies
		providersConfig := rawCfg.Providers

		// Process direct proxies
		for i, config := range proxiesConfig {
			proxy, err := adapter.ParseProxy(config)
			if err != nil {
				logger.LogError("Failed to parse proxy", err,
					slog.Int("proxy_index", i),
					slog.String("config_path", configPath),
				)
				return nil, fmt.Errorf("proxy %d: %w", i, err)
			}

			if _, exist := proxies[proxy.Name()]; exist {
				logger.Logger.Error("Duplicate proxy name found",
					slog.String("proxy_name", proxy.Name()),
					slog.String("config_path", configPath),
				)
				return nil, fmt.Errorf("proxy %s is the duplicate name", proxy.Name())
			}
			proxies[proxy.Name()] = &CProxy{Proxy: proxy, Config: config}
		}

		// Process proxy providers
		for name, config := range providersConfig {
			if name == provider.ReservedName {
				logger.Logger.Error("Reserved provider name used",
					slog.String("provider_name", name),
					slog.String("reserved_name", provider.ReservedName),
				)
				return nil, fmt.Errorf("can not defined a provider called `%s`", provider.ReservedName)
			}

			logger.Logger.Debug("Processing proxy provider",
				slog.String("provider_name", name),
				slog.String("config_path", configPath),
			)

			pd, err := provider.ParseProxyProvider(name, config)
			if err != nil {
				logger.LogError("Failed to parse proxy provider", err,
					slog.String("provider_name", name),
					slog.String("config_path", configPath),
				)
				return nil, fmt.Errorf("parse proxy provider %s error: %w", name, err)
			}
			if err := pd.Initial(); err != nil {
				logger.LogError("Failed to initialize proxy provider", err,
					slog.String("provider_name", name),
				)
				return nil, fmt.Errorf("initial proxy provider %s error: %w", pd.Name(), err)
			}

			resp, err := http.Get(config["url"].(string))
			if err != nil {
				logger.LogError("Failed to fetch provider config", err,
					slog.String("provider_name", name),
					slog.String("provider_url", config["url"].(string)),
				)
				continue
			}
			body, err = io.ReadAll(resp.Body)
			if err != nil {
				logger.LogError("Failed to read provider response", err,
					slog.String("provider_name", name),
				)
				return nil, err
			}
			pdRawCfg := &RawConfig{
				Proxies: []map[string]any{},
			}
			if err := yaml.Unmarshal(body, pdRawCfg); err != nil {
				logger.LogError("Failed to parse provider YAML", err,
					slog.String("provider_name", name),
				)
				return nil, err
			}
			pdProxies := make(map[string]map[string]any)
			for _, pdProxy := range pdRawCfg.Proxies {
				pdProxies[pdProxy["name"].(string)] = pdProxy
			}

			providerProxyCount := 0
			for _, proxy := range pd.Proxies() {
				proxies[fmt.Sprintf("[%s] %s", name, proxy.Name())] = &CProxy{
					Proxy:  proxy,
					Config: pdProxies[proxy.Name()],
				}
				providerProxyCount++
			}

			logger.Logger.Info("Provider proxies loaded",
				slog.String("provider_name", name),
				slog.Int("proxy_count", providerProxyCount),
			)
		}

		// Filter and add proxies to allProxies
		addedCount := 0
		for k, p := range proxies {
			switch p.Type() {
			case constant.Shadowsocks, constant.ShadowsocksR, constant.Snell, constant.Socks5, constant.Http,
				constant.Vmess, constant.Vless, constant.Trojan, constant.Hysteria, constant.Hysteria2,
				constant.WireGuard, constant.Tuic, constant.Ssh, constant.Mieru, constant.AnyTLS:
			default:
				logger.Logger.Debug("Skipping unsupported proxy type",
					slog.String("proxy_name", k),
					slog.String("proxy_type", p.Type().String()),
				)
				continue
			}
			if server, ok := p.Config["server"]; ok {
				p.Config["server"] = convertMappedIPv6ToIPv4(server.(string))
			}
			if stashCompatible && !isStashCompatible(p) {
				logger.Logger.Debug("Skipping proxy not compatible with Stash",
					slog.String("proxy_name", k),
					slog.String("proxy_type", p.Type().String()),
				)
				continue
			}
			if _, ok := allProxies[k]; !ok {
				allProxies[k] = p
				addedCount++
			}
		}

		logger.Logger.Info("Proxies processed from config",
			slog.String("config_path", configPath),
			slog.Int("loaded_count", len(proxies)),
			slog.Int("added_count", addedCount),
		)
	}

	filterRegexp := regexp.MustCompile(st.config.FilterRegex)
	filteredProxies := make(map[string]*CProxy)
	matchedCount := 0

	for name := range allProxies {
		proxy := allProxies[name]

		// Apply regex filter
		if !filterRegexp.MatchString(name) {
			continue
		}

		// Apply include nodes filter
		if len(st.config.IncludeNodes) > 0 {
			includeMatch := false
			for _, include := range st.config.IncludeNodes {
				if strings.TrimSpace(include) == "" {
					continue
				}
				if strings.Contains(strings.ToLower(name), strings.ToLower(strings.TrimSpace(include))) {
					includeMatch = true
					break
				}
			}
			if !includeMatch {
				continue
			}
		}

		// Apply exclude nodes filter
		if len(st.config.ExcludeNodes) > 0 {
			excludeMatch := false
			for _, exclude := range st.config.ExcludeNodes {
				if strings.TrimSpace(exclude) == "" {
					continue
				}
				if strings.Contains(strings.ToLower(name), strings.ToLower(strings.TrimSpace(exclude))) {
					excludeMatch = true
					break
				}
			}
			if excludeMatch {
				continue
			}
		}

		// Apply protocol filter
		if len(st.config.ProtocolFilter) > 0 {
			protocolMatch := false
			proxyType := proxy.Type().String()
			for _, protocol := range st.config.ProtocolFilter {
				if strings.TrimSpace(protocol) == "" {
					continue
				}
				if strings.EqualFold(proxyType, strings.TrimSpace(protocol)) {
					protocolMatch = true
					break
				}
			}
			if !protocolMatch {
				continue
			}
		}

		filteredProxies[name] = proxy
		matchedCount++
	}

	logger.Logger.Info("Proxy loading completed",
		slog.Int("total_loaded", len(allProxies)),
		slog.Int("after_filter", len(filteredProxies)),
		slog.String("filter_regex", st.config.FilterRegex),
		slog.Int("matched_filter", matchedCount),
	)

	return filteredProxies, nil
}

// GetAvailableProtocols returns all unique protocols from loaded proxies
func (st *SpeedTester) GetAvailableProtocols(proxies map[string]*CProxy) []string {
	protocolSet := make(map[string]bool)
	for _, proxy := range proxies {
		protocolSet[proxy.Type().String()] = true
	}

	protocols := make([]string, 0, len(protocolSet))
	for protocol := range protocolSet {
		protocols = append(protocols, protocol)
	}

	return protocols
}

// isStashCompatible checks if proxy is compatible with Stash
func isStashCompatible(proxy *CProxy) bool {
	switch proxy.Type() {
	case constant.Shadowsocks:
		cipher, ok := proxy.Config["cipher"]
		if ok {
			switch cipher {
			case "aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305":
				return true
			}
		}
		return false
	case constant.ShadowsocksR:
		return false
	case constant.Vmess:
		return true
	case constant.Trojan:
		return true
	case constant.Snell:
		return false
	case constant.Http, constant.Socks5:
		return true
	default:
		return false
	}
}

// convertMappedIPv6ToIPv4 converts IPv6-mapped IPv4 addresses to IPv4
func convertMappedIPv6ToIPv4(server string) string {
	if strings.HasPrefix(server, "::ffff:") {
		if ipv4 := net.ParseIP(server); ipv4 != nil {
			if ipv4.To4() != nil {
				return ipv4.To4().String()
			}
		}
	}
	return server
}

// parseURISubscription parses proxy subscription content that is a list of
// share-link URIs (base64-encoded or plaintext), one URI per line. It handles
// the standard schemes via mihomo's converter, then supplements http/https
// proxies that the converter does not support.
func parseURISubscription(body []byte) ([]map[string]any, error) {
	data := convert.DecodeBase64(body)

	proxies, converterErr := convert.ConvertsV2Ray(data)
	proxies = append(proxies, parseHTTPURIs(data)...)

	if len(proxies) == 0 {
		if converterErr != nil {
			return nil, fmt.Errorf("parse v2ray subscription: %w", converterErr)
		}
		return nil, fmt.Errorf("no valid proxy URIs found in subscription")
	}
	return proxies, nil
}

// parseHTTPURIs parses http/https proxy URIs into proxy config maps.
// Example: https://user:pass@host:port?skip-cert-verify=true#name
func parseHTTPURIs(data []byte) []map[string]any {
	proxies := make([]map[string]any, 0)
	names := make(map[string]int)

	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		scheme, _, found := strings.Cut(line, "://")
		if !found {
			continue
		}
		scheme = strings.ToLower(scheme)
		if scheme != "http" && scheme != "https" {
			continue
		}

		u, err := url.Parse(line)
		if err != nil || u.Hostname() == "" {
			continue
		}

		name := u.Fragment
		if name == "" {
			name = u.Hostname()
		}
		name = uniqueProxyName(names, name)

		portStr := u.Port()
		if portStr == "" {
			if scheme == "https" {
				portStr = "443"
			} else {
				portStr = "80"
			}
		}
		port, _ := strconv.Atoi(portStr)

		proxy := map[string]any{
			"name":   name,
			"type":   "http",
			"server": u.Hostname(),
			"port":   port,
		}
		if scheme == "https" {
			proxy["tls"] = true
		}
		if u.User != nil {
			proxy["username"] = u.User.Username()
			if password, ok := u.User.Password(); ok {
				proxy["password"] = password
			}
		}
		if skipVerify, err := strconv.ParseBool(u.Query().Get("skip-cert-verify")); err == nil {
			proxy["skip-cert-verify"] = skipVerify
		}

		proxies = append(proxies, proxy)
	}
	return proxies
}

// uniqueProxyName deduplicates proxy names with a numeric suffix.
func uniqueProxyName(names map[string]int, name string) string {
	if idx, ok := names[name]; ok {
		idx++
		names[name] = idx
		return fmt.Sprintf("%s-%02d", name, idx)
	}
	names[name] = 0
	return name
}
