// Lançador do pacote de casos do Ipê (0.100.56): serve a pasta onde ele está em http://127.0.0.1:<porta>/ e abre o
// navegador. O navegador não abre o visualizador completo direto do disco (file://), por isso este servidorzinho.
// Só atende a este computador (127.0.0.1); nada é instalado e nada sai daqui. Fechar a janela termina.
//
// Compilar (o release faz isso para cada sistema):
//   GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o ipe-casos-windows-amd64.exe
package main

import (
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

func pasta() string {
	if len(flag.Args()) > 0 {
		return flag.Args()[0]
	}
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	if r, err := filepath.EvalSymlinks(exe); err == nil {
		exe = r
	}
	return filepath.Dir(exe)
}

func abrir(url string) error {
	switch runtime.GOOS {
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	case "darwin":
		return exec.Command("open", url).Start()
	default:
		return exec.Command("xdg-open", url).Start()
	}
}

type semCache struct{ h http.Handler }

func (s semCache) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-cache")
	if strings.HasSuffix(r.URL.Path, ".wasm") {
		w.Header().Set("Content-Type", "application/wasm")
	}
	s.h.ServeHTTP(w, r)
}

func main() {
	porta := flag.Int("porta", 0, "porta (0 = a primeira livre a partir de 47810)")
	semNavegador := flag.Bool("sem-navegador", false, "não abrir o navegador")
	flag.Parse()
	raiz := pasta()
	if _, err := os.Stat(filepath.Join(raiz, "casos", "casos.json")); err != nil {
		fmt.Println("Não achei os casos (casos/casos.json) ao lado deste programa:", raiz)
		fmt.Println("Cases not found next to this program. / No se encontraron los casos junto a este programa.")
		time.Sleep(15 * time.Second)
		os.Exit(1)
	}
	var ln net.Listener
	var err error
	if *porta != 0 {
		ln, err = net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", *porta))
	} else {
		for p := 47810; p < 47900; p++ {
			if ln, err = net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", p)); err == nil {
				break
			}
		}
		if ln == nil {
			ln, err = net.Listen("tcp", "127.0.0.1:0")
		}
	}
	if err != nil {
		fmt.Println("Não deu para abrir:", err)
		time.Sleep(15 * time.Second)
		os.Exit(1)
	}
	url := fmt.Sprintf("http://%s/", ln.Addr().String())
	fmt.Println("Ipê — pacote de casos")
	fmt.Println("Abra no navegador / Open in the browser / Abra en el navegador:", url)
	fmt.Println("Deixe esta janela aberta enquanto estiver vendo os casos; feche-a para terminar.")
	fmt.Println("Keep this window open while viewing; close it to finish. / Deje esta ventana abierta; ciérrela para terminar.")
	if !*semNavegador {
		go func() {
			time.Sleep(400 * time.Millisecond)
			if err := abrir(url); err != nil {
				fmt.Println("(não abri o navegador sozinho:", err, ")")
			}
		}()
	}
	srv := &http.Server{Handler: semCache{http.FileServer(http.Dir(raiz))}, ReadHeaderTimeout: 10 * time.Second}
	if err := srv.Serve(ln); err != nil {
		fmt.Println(err)
		time.Sleep(15 * time.Second)
	}
}
