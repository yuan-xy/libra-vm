from .testutils import compile_script_string


def println(str, *args):
    print(str.format(*args))


def test_serialize_script_ret():
    code = """
        main() {
            return;
        }
    """
    compiled_script_res = compile_script_string(code)
    compiled_script = compiled_script_res
    binary = compiled_script.serialize()
    println("SCRIPT:\n{}", compiled_script)
    println("Serialized Script:\n{}", binary)
    println("binary[74]: {}", binary[74])
    println("binary[76]: {}", binary[76])
    println("binary[79]: {}", binary[79])
    println("binary[82]: {}", binary[82])
    println("binary[84]: {}", binary[84])
    println("binary[96]: {}", binary[96])
    println("binary[128]: {}", binary[128])
    println("binary[75]: {}", binary[75])
    println("binary[77]: {}", binary[77])
    println("binary[80]: {}", binary[80])
    println("binary[83]: {}", binary[83])
    println("binary[85]: {}", binary[85])
    println("binary[97]: {}", binary[97])
    println("binary[129]: {}", binary[129])
    # println("SCRIPT:\n{}", compiled_script)
