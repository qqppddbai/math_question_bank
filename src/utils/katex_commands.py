# -*- coding: utf-8 -*-
"""KaTeX 支持的命令名清单（自动生成，请勿手改）。

它的用途：导入题目时先判断公式里有没有 KaTeX 不认识的命令，
提前提醒老师，而不是等入库后在页面上渲染成一片红字。

来源与生成方式
--------------
这份清单不是手抄的，而是从 **Streamlit 内置的 KaTeX** 里抽出来、并用同一个版本
逐条核验过的：

1. Streamlit 用 KaTeX 渲染公式（rehype-katex，`throwOnError: true`）；
   公式一旦解析失败就渲染成 `<span class="katex-error">`，也就是页面上看到的红字。
   本项目自测环境实测内置版本为 **KaTeX 0.16.47**。
2. `npm i katex@0.16.47`，从 `dist/katex.mjs` 和 Streamlit 打包的
   `static/static/js/katex.*.js` 两处扫描所有形如 ``"\\frac"`` 的字符串字面量，
   取并集得到候选命令名。
3. 用同一版 KaTeX 对每个候选跑 `renderToString()`：凡报
   “Undefined control sequence: \\xxx” 的剔除，其余保留 → 共 967 条。
4. 补回 `\\cr`：它只在 array 环境内部合法，单独用会报未定义，
   但写在 array 里是正常的，补进来避免误报。

换 Streamlit / KaTeX 版本后，若发现某个合法命令被误报，按上面 4 步重新生成即可。
"""

# 每条一行太占地方，这里按 8 个一行排开（不含反斜杠前缀）。
_NAMES = """\
    AA Alpha And Bbb Bbbk Beta Big Bigg
    Biggl Biggm Biggr Bigl Bigm Bigr Box Bra
    Braket Bumpeq Cap Chi Colonapprox Coloneq Coloneqq Colonsim
    Complex Cup DOTSB DOTSI DOTSX Dagger Darr Delta
    Diamond Doteq Downarrow Epsilon Eqcolon Eqqcolon Eta Finv
    Game Gamma Harr Huge Im Iota Join KaTeX
    Kappa Ket LARGE LaTeX Lambda Large Larr Leftarrow
    Leftrightarrow Lleftarrow Longleftarrow Longleftrightarrow Longrightarrow Lrarr Lsh Mu
    Nu Omega Omicron Overrightarrow Phi Pi Pr Psi
    Rarr Re Reals Rho Rightarrow Rrightarrow Rsh Set
    Sigma Subset Supset Tau TeX TextOrMath Theta Uarr
    Uparrow Updownarrow Upsilon Vdash Vert Vvdash Xi Zeta
    aa above acute alef alefsym aleph allowbreak alpha
    amalg angl angle angln approx approxcolon approxcoloncolon approxeq
    arccos arcctg arcsin arctan arctg arg argmax argmin
    ast asymp atop backepsilon backprime backsim backsimeq backslash
    bar barwedge bcancel because begin begingroup beta beth
    between bf bgroup big bigcap bigcirc bigcup bigg
    biggl biggm biggr bigl bigm bigodot bigoplus bigotimes
    bigr bigsqcup bigstar bigtriangledown bigtriangleup biguplus bigvee bigwedge
    binom blacklozenge blacksquare blacktriangle blacktriangledown blacktriangleleft blacktriangleright blue
    blueA blueB blueC blueD blueE bm bmod bold
    boldsymbol bot bowtie boxdot boxed boxminus boxplus boxtimes
    bra brace brack braket breve bull bullet bumpeq
    cal cancel cap cdot cdotp cdots centerdot cfrac
    ch char check checkmark chi choose circ circeq
    circlearrowleft circlearrowright circledR circledS circledast circledcirc circleddash clap
    clubs clubsuit cnums colon colonapprox coloncolon coloncolonapprox coloncolonequals
    coloncolonminus coloncolonsim coloneq coloneqq colonequals colonminus colonsim color
    colorbox complement cong coprod copyright cos cosec cosh
    cot cotg coth csc ctg cth cup curlyeqprec
    curlyeqsucc curlyvee curlywedge curvearrowleft curvearrowright dArr dag dagger
    daleth darr dashleftarrow dashrightarrow dashv dbinom dblcolon ddag
    ddagger ddddot dddot ddot ddots def deg degree
    delta det dfrac diagdown diagup diamond diamonds diamondsuit
    digamma dim displaystyle div divideontimes dot doteq doteqdot
    dotplus dots dotsb dotsc dotsi dotsm dotso dotsx
    doublebarwedge doublecap doublecup downarrow downdownarrows downharpoonleft downharpoonright edef
    egroup ell emph empty emptyset end endgroup enskip
    enspace epsilon eqcirc eqcolon eqqcolon eqsim eqslantgtr eqslantless
    equalscolon equalscoloncolon equiv errmessage eta eth exist exists
    exp expandafter fallingdotseq fbox fcolorbox flat footnotesize forall
    frac frak frown futurelet gamma gcd gdef ge
    genfrac geq geqq geqslant gets gg ggg gggtr
    gimel global gnapprox gneq gneqq gnsim goldA goldB
    goldC goldD goldE grave gray grayA grayB grayC
    grayD grayE grayF grayG grayH grayI green greenA
    greenB greenC greenD greenE gt gtrapprox gtrdot gtreqless
    gtreqqless gtrless gtrsim gvertneqq hArr harr hat hbar
    hbox hdashline hearts heartsuit hline hom hookleftarrow hookrightarrow
    hphantom href hskip hslash hspace htmlClass htmlData htmlId
    htmlStyle huge iff iiint iint image imageof imath
    impliedby implies in includegraphics inf infin infty injlim
    int intercal intop iota isin it jmath kaBlue
    kaGreen kappa ker kern ket lArr lBrace lVert
    lambda land lang langle large larr lbrace lbrack
    lceil ldotp ldots le leadsto left leftarrow leftarrowtail
    leftharpoondown leftharpoonup leftleftarrows leftrightarrow leftrightarrows leftrightharpoons leftrightsquigarrow leftthreetimes
    leq leqq leqslant lessapprox lessdot lesseqgtr lesseqqgtr lessgtr
    lesssim let lfloor lg lgroup lhd lim liminf
    limits limsup ll llap llbracket llcorner lll llless
    lmoustache ln lnapprox lneq lneqq lnot lnsim log
    long longleftarrow longleftrightarrow longmapsto longrightarrow looparrowleft looparrowright lor
    lozenge lparen lq lrArr lrarr lrcorner lt ltimes
    lvert lvertneqq maltese mapsto maroonA maroonB maroonC maroonD
    maroonE mathbb mathbf mathbin mathcal mathchoice mathclap mathclose
    mathellipsis mathfrak mathinner mathit mathllap mathnormal mathop mathopen
    mathord mathpunct mathrel mathring mathrlap mathrm mathscr mathsf
    mathsfit mathsterling mathstrut mathtt max measuredangle medspace message
    mho mid middle min mintA mintB mintC minuscolon
    minuscoloncolon minuso mkern mod models mp mskip mu
    multimap nLeftarrow nLeftrightarrow nRightarrow nVDash nVdash nabla natnums
    natural ncong ne nearrow neg negmedspace negthickspace negthinspace
    neq newcommand newline nexists ngeq ngeqq ngeqslant ngtr
    ni nleftarrow nleftrightarrow nleq nleqq nleqslant nless nmid
    nobreak nobreakspace noexpand nolimits nonumber normalsize not notag
    notin notni nparallel nprec npreceq nrightarrow nshortmid nshortparallel
    nsim nsubseteq nsubseteqq nsucc nsucceq nsupseteq nsupseteqq ntriangleleft
    ntrianglelefteq ntriangleright ntrianglerighteq nu nvDash nvdash nwarrow odot
    oiiint oiint oint omega omicron ominus operatorname operatornamewithlimits
    oplus orange ordinarycolon origof oslash otimes over overbrace
    overbracket overgroup overleftarrow overleftharpoon overleftrightarrow overline overlinesegment overrightarrow
    overrightharpoon overset owns parallel partial perp phantom phase
    phi pi pink pitchfork plim plusmn pm pmb
    pmod pod pounds prec precapprox preccurlyeq preceq precnapprox
    precneqq precnsim precsim prime prod projlim propto providecommand
    psi purple purpleA purpleB purpleC purpleD purpleE qquad
    quad rArr rBrace rVert raisebox rang rangle rarr
    ratio rbrace rbrack rceil real reals red redA
    redB redC redD redE relax renewcommand restriction rfloor
    rgroup rhd rho right rightarrow rightarrowtail rightharpoondown rightharpoonup
    rightleftarrows rightleftharpoons rightrightarrows rightsquigarrow rightthreetimes risingdotseq rlap rm
    rmoustache rparen rq rrbracket rtimes rule rvert scriptscriptstyle
    scriptsize scriptstyle sdot searrow sec sect set setminus
    sf sh sharp shortmid shortparallel show sigma sim
    simcolon simcoloncolon simeq sin sinh sixptsize small smallfrown
    smallint smallsetminus smallsmile smash smile sout space spades
    spadesuit sphericalangle sqcap sqcup sqrt sqsubset sqsubseteq sqsupset
    sqsupseteq square stackrel star sub sube subset subseteq
    subseteqq subsetneq subsetneqq substack succ succapprox succcurlyeq succeq
    succnapprox succneqq succnsim succsim sum sup supe supset
    supseteq supseteqq supsetneq supsetneqq surd swarrow tag tan
    tanh tau tbinom tealA tealB tealC tealD tealE
    text textbf textcircled textcolor textcopyright textit textmd textnormal
    textregistered textrm textsf textstyle texttt textup tfrac tg
    th therefore theta thetasym thickapprox thicksim thickspace thinspace
    tilde times tiny tmspace to top triangle triangledown
    triangleleft trianglelefteq triangleq triangleright trianglerighteq tt twoheadleftarrow twoheadrightarrow
    uArr uarr ulcorner underbar underbrace underbracket undergroup underleftarrow
    underleftrightarrow underline underlinesegment underrightarrow underset unlhd unrhd uparrow
    updownarrow upharpoonleft upharpoonright uplus upsilon upuparrows urcorner url
    utilde vDash varDelta varGamma varLambda varOmega varPhi varPi
    varPsi varSigma varTheta varUpsilon varXi varepsilon varinjlim varkappa
    varliminf varlimsup varnothing varphi varpi varprojlim varpropto varrho
    varsigma varsubsetneq varsubsetneqq varsupsetneq varsupsetneqq vartheta vartriangle vartriangleleft
    vartriangleright varvdots vcentcolon vcenter vdash vdots vec vee
    veebar verb vert vphantom wedge weierp widecheck widehat
    widetilde wp wr xLeftarrow xLeftrightarrow xRightarrow xcancel xdef
    xhookleftarrow xhookrightarrow xi xleftarrow xleftequilibrium xleftharpoondown xleftharpoonup xleftrightarrow
    xleftrightharpoons xlongequal xmapsto xrightarrow xrightequilibrium xrightharpoondown xrightharpoonup xrightleftarrows
    xrightleftharpoons xtofrom xtwoheadleftarrow xtwoheadrightarrow yen zeta
"""

#: KaTeX 认识的命令名集合，元素带反斜杠前缀，例如 "\\frac"。
KATEX_COMMANDS = frozenset("\\" + _n for _n in _NAMES.split())

#: 只在特定环境里合法的名字，补进来避免误报（见文件头第 4 步）。
CONTEXTUAL_COMMANDS = frozenset({"\\cr"})


def is_known_command(name: str) -> bool:
    """判断 ``\\frac`` 这种写法在 KaTeX 里是否已定义。

    name 可以带或不带反斜杠前缀。
    """
    if not name.startswith("\\"):
        name = "\\" + name
    return name in KATEX_COMMANDS or name in CONTEXTUAL_COMMANDS


__all__ = ["KATEX_COMMANDS", "CONTEXTUAL_COMMANDS", "is_known_command"]
