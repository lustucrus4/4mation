pub const ZOBRIST_CELL: [u64; 147] = [
    // (0, 0, 0)
    0x1c80317fa3b1799d,
    0xbdd640fb06671ad1,
    0x3eb13b9046685257,
    // (0, 1, 0)
    0x23b8c1e9392456de,
    0x1a3d1fa7bc8960a9,
    0xbd9c66b3ad3c2d6d,
    // (0, 2, 0)
    0x8b9d2434e465e150,
    0x972a846916419f82,
    0x0822e8f36c031199,
    // (0, 3, 0)
    0x17fc695a07a0ca6e,
    0x3b8faa1837f8a88b,
    0x9a1de644815ef6d1,
    // (0, 4, 0)
    0x8fadc1a606cb0fb3,
    0xb74d0fb132e70629,
    0xb38a088ca65ed389,
    // (0, 5, 0)
    0x6b65a6a48b8148f6,
    0x72ff5d2a386ecbe0,
    0x4737819096da1dac,
    // (0, 6, 0)
    0xde8a774bcf36d58b,
    0xc241330b01a9e71f,
    0x28df6ec4ce4a2bbd,
    // (1, 0, 0)
    0x6c307511b2b9437a,
    0x47229389571aa876,
    0x371ecd7b27cd8130,
    // (1, 1, 0)
    0xc37459eef50bea63,
    0x1a2a73ed562b0f79,
    0x6142ea7d17be3111,
    // (1, 2, 0)
    0x5be6128e18c26797,
    0x580d7b71d8f56413,
    0x43b7a3a69a8dca03,
    // (1, 3, 0)
    0x0b1f9163ce9ff57f,
    0x759cde66bacfb3d0,
    0x1ff49b7889463e85,
    // (1, 4, 0)
    0xec1b8ca1f91e1d4c,
    0x142c3fe860e7a113,
    0x4b0dbb418d5288f1,
    // (1, 5, 0)
    0xa0ee89aed453dd32,
    0xe2acf72f9e574f7a,
    0x5c941cf0dc98d2c1,
    // (1, 6, 0)
    0x3139d32c93cd59bf,
    0x11ce5dd2b45ed1f0,
    0xa9488d990bbb2599,
    // (2, 0, 0)
    0xc5e7ce8a3a578a8e,
    0xfc377a4c4a15544d,
    0xdaf61a26146d3f31,
    // (2, 1, 0)
    0xddd1dfb23b982ef8,
    0x614ff3d719db3ad0,
    0x7412b29347294739,
    // (2, 2, 0)
    0xd58842dea2bc372f,
    0x29a3b2e95d65a441,
    0x5af305535ec42e08,
    // (2, 3, 0)
    0xab9099a435a240ae,
    0xb3aa7efe4458a885,
    0xaefcfad8efc89849,
    // (2, 4, 0)
    0x12476f57a5e5a5ab,
    0xa28defe39bf00273,
    0x88bd64072bcfbe01,
    // (2, 5, 0)
    0x3eabedcbbaa80dd4,
    0x7656af7229d4beef,
    0x451b4cf36123fdf7,
    // (2, 6, 0)
    0xece66fa2fd5166e6,
    0xb02b61c4a3d70628,
    0x3838b3268e944239,
    // (3, 0, 0)
    0x5304317faf42e12f,
    0xc4b032ccd7c524a5,
    0x0e51f30dc6a7ee39,
    // (3, 1, 0)
    0xd261a7ab3aa2e4f9,
    0xce177b4e0837b8a3,
    0x66b2bc5b50c187fc,
    // (3, 2, 0)
    0x10f1bc81448aaa9e,
    0xe9c349e03602f8ac,
    0x9132b63ef16287e4,
    // (3, 3, 0)
    0xb7c93acfe059a0ee,
    0x366eb16f508ebad7,
    0x7fcd9eb1a7cad415,
    // (3, 4, 0)
    0xe27a984d654821d0,
    0xa491f0b2ea1fca65,
    0x24933b83757750a9,
    // (3, 5, 0)
    0x23bed01d43cf2fde,
    0xbeb799193f22faf8,
    0x89fa6a688fb5d27b,
    // (3, 6, 0)
    0xbf3c4c06434308bc,
    0x6dadd6c795a76d79,
    0x956269f0e5d7b875,
    // (4, 0, 0)
    0x5cabcc97663f1c97,
    0xff50bde4382567b8,
    0x2369b584ff5e9ff0,
    // (4, 1, 0)
    0x7e570ddf827050a8,
    0xc17af08a1745d6d8,
    0xdc713d960c0fd195,
    // (4, 2, 0)
    0x27209bdf1c11f735,
    0x28f49481a0a04dc4,
    0xae340454cac5b68c,
    // (4, 3, 0)
    0x98ae43346c12ace8,
    0x62801c4510435a10,
    0x988c24c961b1cd22,
    // (4, 4, 0)
    0x77d21e02ff01cf99,
    0x405cacec877409a9,
    0x8da0365bf89897b9,
    // (4, 5, 0)
    0xf143262fdc5c0eed,
    0xae270da702f06b90,
    0x1d53434bb88139b9,
    // (4, 6, 0)
    0xe2817efdae849217,
    0xc03987108976e334,
    0xc4c2e2e3444ea7c8,
    // (5, 0, 0)
    0x5715bd6fa4161293,
    0x4b22d3081c8eaee9,
    0x287d06ca6f4cc69a,
    // (5, 1, 0)
    0x00d4af5974273ca3,
    0xb8db0672f42d47cc,
    0xb83cfe0be037e5ed,
    // (5, 2, 0)
    0xf8cda88b436d76e2,
    0xc30ff46e8026695f,
    0x81f76d1c2dbc2134,
    // (5, 3, 0)
    0x1b3dbd5ce9a1fa6f,
    0xa013ac6ededa4e16,
    0xd777a4774c66e0a8,
    // (5, 4, 0)
    0x81f631d4a39231a7,
    0x32ebd6899be578c7,
    0x5fb8d16c2720797d,
    // (5, 5, 0)
    0x295b4715c333e861,
    0xf4188f3f8a14be62,
    0xec24a3c5c754108f,
    // (5, 6, 0)
    0xeb2263dd87c5421e,
    0x99546eb400257ad1,
    0x7d15438552fbe43b,
    // (6, 0, 0)
    0x1ca35cfb04fc6d82,
    0x5cec4eb5edd96831,
    0xfc3e058be0f3eab0,
    // (6, 1, 0)
    0xce88cb2dd4e80839,
    0x3d4cbf374eb93eff,
    0x3da9c2a90ed42f1a,
    // (6, 2, 0)
    0x913e4de2e0c53cb8,
    0x14296c07f26b4776,
    0xbb5e4bcf15ed6269,
    // (6, 3, 0)
    0xd0e6e6607c69dee1,
    0xfa5d310011b7e948,
    0x885f6e66c2b6d2c5,
    // (6, 4, 0)
    0x2031d750c40db9b4,
    0xa8e56e0c20de435d,
    0xf264accc79ac1b1e,
    // (6, 5, 0)
    0x2a45c2ab8cbfedb0,
    0x8715a10343dac043,
    0x9b49bd26df57c59a,
    // (6, 6, 0)
    0xf6e07cc06c52c49f,
    0xedcd465e36386821,
    0xc1590f538a0f4efb
];
pub const ZOBRIST_P1: u64 = 0xb09b2a5cbadcc32a;
pub const ZOBRIST_P2: u64 = 0xb683d2e6337ea2df;