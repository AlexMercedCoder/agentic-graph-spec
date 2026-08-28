package ags

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"

	"github.com/gowebpki/jcs"
)

func CanonicalJSON(value any) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return jcs.Transform(raw)
}

func GraphDigest(document Document) (string, error) {
	canonical, err := CanonicalJSON(document)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(canonical)
	return "sha256-" + base64.StdEncoding.EncodeToString(sum[:]), nil
}

func MustGraphDigest(document Document) string {
	digest, err := GraphDigest(document)
	if err != nil {
		panic(fmt.Sprintf("AGS graph digest: %v", err))
	}
	return digest
}
