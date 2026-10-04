from genlayer_doctor.diagnose import classify, findings_from_genvm_error, parse_genvm_error, traceback_tail


def test_parse_real_floating_runner_error(fixture):
    msg = fixture("schema_bad_header.json")["error"]["message"]
    err = parse_genvm_error(msg)
    assert err.summary == "execution failed"
    assert err.result_kind == "VM_ERROR" and err.result_message == "invalid_contract"
    assert ":test/ :latest runner used in non-debug mode, this is not allowed" in err.log_warnings
    assert err.genvm_version.startswith("v0.")
    # noise is filtered
    assert not any("backtrace" in w or "does not start with version" in w for w in err.log_warnings)
    [f] = findings_from_genvm_error(err, "dry run")
    assert f.code == "GLD004" and f.severity == "error"


def test_parse_real_syntax_error(fixture):
    err = parse_genvm_error(fixture("schema_syntax_error.json")["error"]["message"])
    assert "SyntaxError" in err.stderr
    tail = traceback_tail(err.stderr)
    assert tail[0].strip().startswith('File "/contract.py", line 18')
    assert findings_from_genvm_error(err, "x")[0].code == "GLD210"


def test_regex_fallback_for_unparseable_message():
    msg = ("('execution failed', {'stderr': '', 'genvm_log': [{'message': 'something odd', 'level': 'warn'}], "
           "'result': '{\"kind\": \"VM_ERROR\", \"message\": \"invalid_contract\"}', 'broken': <object>})")
    err = parse_genvm_error(msg)
    assert err.result_message == "invalid_contract"
    assert "something odd" in err.log_warnings
    assert findings_from_genvm_error(err, "x")[0].code == "GLD201"


def test_classify_order_and_unknown():
    assert classify("ModuleNotFoundError: No module named 'requests'")[0] == "GLD211"
    assert classify("exit_code 1")[0] == "GLD214"
    assert classify("totally new failure") is None
    assert findings_from_genvm_error(parse_genvm_error("weird"), "x")[0].code == "GLD299"
