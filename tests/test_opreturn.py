"""Tests for OP_RETURN header encoding and decoding."""

import pytest

from digirails._opreturn import (
    decode_header,
    encode_attestation,
    encode_header,
    encode_identity_declaration,
    encode_identity_transfer,
    encode_payment_memo,
    encode_service_declaration,
    manifest_hash,
)
from digirails.network.constants import DR_VERSION, DR_TEST_FLAG, SubProtocol


class TestHeader:
    def test_encode_drpay_service_declaration(self):
        header = encode_header(SubProtocol.DR_PAY, 0x01)
        assert header == b"\x44\x52\x01\x01\x01"
        assert len(header) == 5

    def test_encode_drcore_identity(self):
        header = encode_header(SubProtocol.DR_CORE, 0x01)
        assert header == b"\x44\x52\x01\x00\x01"

    def test_decode_valid(self):
        data = b"\x44\x52\x01\x01\x02" + b"payload"
        result = decode_header(data)
        assert result is not None
        ver, sp, mt, payload, is_test = result
        assert ver == DR_VERSION
        assert sp == SubProtocol.DR_PAY
        assert mt == 0x02
        assert payload == b"payload"
        assert is_test is False

    def test_decode_too_short(self):
        assert decode_header(b"\x44\x52\x01") is None

    def test_decode_wrong_magic(self):
        assert decode_header(b"\x00\x00\x01\x01\x01") is None


class TestTestFlag:
    def test_encode_with_test_flag(self):
        header = encode_header(SubProtocol.DR_PAY, 0x01, test=True)
        assert header == b"\x44\x52\x81\x01\x01"
        assert header[2] == DR_VERSION | DR_TEST_FLAG

    def test_encode_without_test_flag(self):
        header = encode_header(SubProtocol.DR_PAY, 0x01, test=False)
        assert header[2] == DR_VERSION

    def test_decode_test_flag(self):
        data = b"\x44\x52\x81\x01\x02" + b"data"
        result = decode_header(data)
        assert result is not None
        ver, sp, mt, payload, is_test = result
        assert ver == DR_VERSION
        assert is_test is True
        assert sp == SubProtocol.DR_PAY
        assert mt == 0x02
        assert payload == b"data"

    def test_decode_production(self):
        data = b"\x44\x52\x01\x01\x02"
        result = decode_header(data)
        assert result is not None
        ver, _, _, _, is_test = result
        assert ver == DR_VERSION
        assert is_test is False

    def test_roundtrip_test_flag(self):
        header = encode_header(SubProtocol.DR_REP, 0x01, test=True)
        result = decode_header(header)
        assert result is not None
        ver, sp, mt, _, is_test = result
        assert ver == DR_VERSION
        assert sp == SubProtocol.DR_REP
        assert mt == 0x01
        assert is_test is True

    def test_roundtrip_production(self):
        header = encode_header(SubProtocol.DR_CORE, 0x02, test=False)
        result = decode_header(header)
        assert result is not None
        ver, sp, mt, _, is_test = result
        assert ver == DR_VERSION
        assert sp == SubProtocol.DR_CORE
        assert mt == 0x02
        assert is_test is False

    def test_version_extraction_strips_flag(self):
        """Version should be extracted from lower 7 bits only."""
        # Manually craft a byte with test flag set and version 1
        data = bytes([0x44, 0x52, 0x81, 0x01, 0x01])
        result = decode_header(data)
        assert result is not None
        assert result[0] == 1  # version is 1, not 0x81


class TestIdentity:
    def test_declaration_empty_label(self):
        data = encode_identity_declaration("")
        assert len(data) == 5  # header only
        result = decode_header(data)
        assert result is not None
        assert result[1] == SubProtocol.DR_CORE
        assert result[2] == 0x01

    def test_declaration_with_label(self):
        data = encode_identity_declaration("my-agent")
        assert len(data) == 5 + 8
        assert data[5:] == b"my-agent"

    def test_declaration_label_too_long(self):
        with pytest.raises(ValueError, match="Label too long"):
            encode_identity_declaration("x" * 76)

    def test_transfer(self):
        addr_hash = b"\x01" * 20
        data = encode_identity_transfer(addr_hash)
        assert len(data) == 25
        assert data[5:] == addr_hash

    def test_transfer_invalid_length(self):
        with pytest.raises(ValueError):
            encode_identity_transfer(b"\x01" * 15)


class TestServiceDeclaration:
    def test_encode(self):
        mhash = b"\xaa" * 32
        data = encode_service_declaration(0x0001, 0x0000, mhash)
        assert len(data) == 41
        # Verify category bytes
        assert data[5:7] == b"\x00\x01"
        # Verify flags
        assert data[7:9] == b"\x00\x00"
        # Verify hash
        assert data[9:] == mhash

    def test_wrong_hash_length(self):
        with pytest.raises(ValueError):
            encode_service_declaration(0x0001, 0x0000, b"\x00" * 16)


class TestPaymentMemo:
    def test_encode_minimal(self):
        invoice_id = b"\x01" * 16
        data = encode_payment_memo(invoice_id)
        assert len(data) == 21  # 5 header + 16 invoice_id

    def test_encode_with_ref(self):
        invoice_id = b"\x02" * 16
        ref = b"echo-service"
        data = encode_payment_memo(invoice_id, ref)
        assert len(data) == 21 + len(ref)

    def test_invalid_invoice_id_length(self):
        with pytest.raises(ValueError):
            encode_payment_memo(b"\x00" * 8)

    def test_ref_too_long(self):
        with pytest.raises(ValueError):
            encode_payment_memo(b"\x00" * 16, b"x" * 60)


class TestAttestation:
    def test_encode(self):
        target = b"\x03" * 20
        data = encode_attestation(target, score=200, nonce=12345)
        assert len(data) == 30

    def test_invalid_score(self):
        with pytest.raises(ValueError):
            encode_attestation(b"\x00" * 20, score=256, nonce=0)

    def test_invalid_target(self):
        with pytest.raises(ValueError):
            encode_attestation(b"\x00" * 10, score=128, nonce=0)


class TestManifestHash:
    def test_deterministic(self):
        json_str = '{"drpay":"0.2.0","address":"dgb1qtest"}'
        h1 = manifest_hash(json_str)
        h2 = manifest_hash(json_str)
        assert h1 == h2
        assert len(h1) == 32
