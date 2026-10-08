from django.db import migrations

TRANSLATIONS = {
    "getting-started": {
        "title": "Primeiros Passos",
        "description": "Um passo a passo de configuração de 3 minutos para novos administradores.",
        "steps": {
            1: {
                "title": "Bem-vindo ao Horilla 👋",
                "description": "Vamos deixar seu sistema de RH pronto em algumas etapas rápidas. Isso leva cerca de três minutos — você pode pular e retomar quando quiser.",
            },
            2: {
                "title": "Etapa 1 — Adicione os dados da sua empresa",
                "description": "Abra Configurações → Empresas para definir o nome, logotipo, endereço e fuso horário da sua empresa. Isso personaliza todo o ambiente de trabalho.",
            },
            3: {
                "title": "Etapa 2 — Crie departamentos e cargos",
                "description": "Em Configurações → Base, adicione seus Departamentos e Cargos para que os funcionários sejam posicionados corretamente e os relatórios façam sentido.",
            },
            4: {
                "title": "Etapa 3 — Configure o e-mail (importante)",
                "description": "Abra Configurações → Configuração do Servidor de E-mail. Sem isso, redefinições de senha, convites de funcionários e notificações não podem ser entregues.",
            },
            5: {
                "title": "Etapa 4 — Adicione sua equipe",
                "description": "Acesse Funcionários para adicionar pessoas uma a uma ou importá-las em massa. Cada funcionário recebe seu próprio login e portal de autoatendimento.",
            },
            6: {
                "title": "Tudo pronto!",
                "description": "Clique neste botão de ajuda a qualquer momento para reproduzir um tour novamente ou iniciar outro.",
            },
        },
    },
    "dashboard-overview": {
        "title": "Visão Geral do Painel",
        "description": "Uma rápida olhada no painel inicial do seu Horilla.",
        "steps": {
            1: {
                "title": "Seu painel",
                "description": "Esta é sua base principal. KPIs, gráficos e ações rápidas são atualizados automaticamente conforme sua equipe usa o Horilla.",
            },
            2: {
                "title": "Faça um tour quando quiser",
                "description": "Abra tours guiados a partir deste botão de ajuda sempre que precisar relembrar um recurso.",
            },
        },
    },
    "dashboard-highlights": {
        "title": "Destaques do Painel",
        "description": "Uma visão guiada do seu painel, ancorada em elementos reais da tela.",
        "steps": {
            1: {
                "title": "Navegação",
                "description": "Todos os módulos de RH ficam nesta barra lateral — Funcionários, Presença, Licença, Folha de Pagamento, Recrutamento e muito mais.",
            },
            2: {
                "title": "Principais métricas em um só olhar",
                "description": "Número de funcionários, taxa de presença, pessoas em licença e aprovações pendentes são atualizados em tempo real aqui.",
            },
            3: {
                "title": "Personalize do seu jeito",
                "description": "Personalize o painel — adicione, oculte ou reorganize cartões de acordo com o funcionamento da sua equipe.",
            },
            4: {
                "title": "Gráficos em tempo real",
                "description": "Detalhamentos visuais (por departamento, gênero, contratações, folha de pagamento…) são atualizados automaticamente conforme seus dados crescem.",
            },
            5: {
                "title": "Aja sem sair do painel",
                "description": "Aprove ou rejeite solicitações de licença, presença e outras diretamente do painel.",
            },
            6: {
                "title": "Barra superior",
                "description": "Busca global, notificações, alternador de empresas e seu perfil ficam todos aqui em cima.",
            },
            7: {
                "title": "Reproduza quando quiser",
                "description": "Abra este botão de Ajuda para reiniciar este tour ou iniciar qualquer outro tour guiado.",
            },
        },
    },
    "employee-directory": {
        "title": "Diretório de Funcionários",
        "description": "Um tour guiado pelo diretório de Funcionários — adicionando, pesquisando e gerenciando a equipe.",
        "steps": {
            1: {
                "title": "Seu Diretório de Funcionários",
                "description": "É aqui que toda pessoa da sua organização está cadastrada. Adicione, filtre, pesquise e gerencie toda a sua equipe em um só lugar.",
            },
            2: {
                "title": "Lista de Funcionários",
                "description": "Cada linha ou cartão mostra um funcionário com nome, cargo, departamento, tipo de trabalho e administrador. Clique em qualquer item para abrir o perfil completo — informações pessoais, documentos, presença, holerites e muito mais.",
            },
            3: {
                "title": "Criar Funcionário",
                "description": "Clique em Criar para adicionar um novo funcionário. Preencha os dados pessoais, atribua um cargo, departamento, administrador e tipo de trabalho. Depois de salvo, o funcionário aparece imediatamente no diretório.",
            },
            4: {
                "title": "Ações",
                "description": "Clique em Ações para acessar operações em massa — Importar funcionários de Excel ou CSV, Exportar a lista atual, Arquivar ou Desarquivar funcionários, enviar E-mail em Massa, realizar Atualizações em Massa ou Excluir os registros selecionados.",
            },
            5: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Alterne entre a visualização em Lista — uma tabela de funcionários — e a visualização em Cartão — uma grade de cartões de perfil — usando os botões de visualização. Ambas as visualizações suportam pesquisa e filtro.",
            },
            6: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Departamento, Cargo, Administrador, Tipo de Trabalho e outras — para focar nos dados que você precisa.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar funcionários por nome. A lista é atualizada conforme você digita — útil quando seu diretório é grande e você precisa localizar alguém rapidamente.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir o diretório por departamento, cargo, tipo de trabalho, administrador, empresa ou status de vínculo. Use Agrupar Por para organizar os funcionários por departamento ou administrador responsável.",
            },
        },
    },
    "ess-dashboard-tour": {
        "title": "Meu Painel",
        "description": "Um tour guiado pelo painel de autoatendimento do funcionário.",
        "steps": {
            1: {
                "title": "Seu painel pessoal",
                "description": "Este é o seu centro de autoatendimento de RH. Veja sua presença, saldo de licença, holerites e solicitações — tudo em um só lugar.",
            },
            2: {
                "title": "Principais métricas",
                "description": "Sua taxa de presença, saldo de licença e solicitações abertas são resumidos aqui em um só olhar.",
            },
            3: {
                "title": "Saldo de licença",
                "description": "Veja seus dias aprovados e restantes para cada tipo de licença. Clique no gráfico para solicitar uma licença.",
            },
            4: {
                "title": "Calendário de presença",
                "description": "Sua presença é registrada dia a dia. Verde significa presente, âmbar significa atrasado, vermelho significa ausente.",
            },
            5: {
                "title": "Minhas solicitações",
                "description": "Verifique aqui mesmo o status das suas solicitações de licença, correções de presença e outras solicitações.",
            },
        },
    },
    "recruitment-pipeline": {
        "title": "Fluxo de Recrutamento",
        "description": "Um tour guiado pelo fluxo de recrutamento — etapas, candidatos e processo de contratação.",
        "steps": {
            1: {
                "title": "O Fluxo de Recrutamento",
                "description": "A página do Fluxo é o seu espaço de trabalho central para contratações. Cada vaga ativa é uma aba, e dentro de cada aba os candidatos avançam por etapas — Inscrito, Pré-selecionado, Entrevista, Proposta, Contratado — representadas como colunas.",
            },
            2: {
                "title": "Quadro do Fluxo",
                "description": "A área do quadro do fluxo exibe todos os recrutamentos ativos como abas. Alterne entre a visualização em Cartão (kanban) e a visualização em Lista usando os botões no canto superior direito para mudar como as colunas de etapas são exibidas.",
            },
            3: {
                "title": "Abas de Recrutamento",
                "description": "Cada aba representa uma vaga ativa. Clique em uma aba para focar no fluxo daquele recrutamento — suas colunas de etapas e cartões de candidatos são carregados abaixo. O indicador em cada aba mostra quantas etapas ela contém.",
            },
            4: {
                "title": "Ações de Recrutamento",
                "description": "Clique nos três pontos (⋮) em qualquer aba de recrutamento para acessar suas ações — Adicionar Etapa, Editar os detalhes do recrutamento, Retomar Pré-seleção para enviar currículos em massa, Gerenciar Ordem das Etapas ou Encerrar o recrutamento.",
            },
            5: {
                "title": "Coluna de Etapa",
                "description": "Cada cabeçalho de coluna mostra o nome da etapa. Na visualização em lista, clique no cabeçalho para recolher ou expandir essa etapa. Na visualização em cartão, arraste o cabeçalho para reordenar as etapas. Clique nos três pontos no cabeçalho para adicionar candidatos, editar ou excluir a etapa.",
            },
            6: {
                "title": "Criar Recrutamento",
                "description": "Clique em Criar para abrir um novo recrutamento. Defina o cargo, os administradores responsáveis pela contratação, o número de vagas e as etapas do fluxo. Depois de publicado, uma página pública de vaga é gerada automaticamente para que os candidatos se inscrevam.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar candidatos por nome em todas as etapas. O fluxo é atualizado conforme você digita — útil quando há muitos candidatos e você precisa localizar alguém rapidamente.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir o fluxo por etapa, status do candidato, agenda de entrevistas, cargo ou administrador do recrutamento. Combine filtros para focar exatamente no subconjunto de candidatos que você precisa revisar.",
            },
        },
    },
    "leave-management": {
        "title": "Gestão de Licenças",
        "description": "Um tour guiado pelas políticas de licença, solicitações e o calendário da equipe.",
        "steps": {
            1: {
                "title": "Gestão de Licenças",
                "description": "Gerencie políticas de licença, aprove solicitações e acompanhe quem está ausente — tudo em um único painel.",
            },
            2: {
                "title": "Métricas de licença",
                "description": "Indicadores principais no topo: total de licenças tiradas, quem está de licença hoje, próximas solicitações e utilização de licenças.",
            },
            3: {
                "title": "Quem está de licença hoje",
                "description": "Veja uma lista em tempo real dos funcionários atualmente de licença para planejar em torno das ausências.",
            },
            4: {
                "title": "Próximas licenças",
                "description": "Planeje-se com antecedência com uma lista de licenças aprovadas que começam nos próximos dias.",
            },
            5: {
                "title": "Personalize o painel",
                "description": "Adicione, remova ou reorganize os gráficos e painéis para focar no que é mais importante para sua equipe.",
            },
            6: {
                "title": "Tipos de Licença e Atribuir Licença",
                "description": "Defina a política de licenças da sua empresa em Tipos de Licença e, em seguida, use Atribuir Licença para conceder saldos iniciais aos funcionários.",
            },
        },
    },
    "attendance-tracking": {
        "title": "Monitoramento de Presença",
        "description": "Um tour guiado pelo monitoramento de presença, registros e solicitações de correção.",
        "steps": {
            1: {
                "title": "Painel de Presença",
                "description": "Monitore pontualidade, atrasos, horas extras e absenteísmo de toda a sua equipe a partir daqui.",
            },
            2: {
                "title": "KPIs em tempo real",
                "description": "Funcionários presentes, atrasos, ausências e horas extras — tudo atualizado em tempo real.",
            },
            3: {
                "title": "Personalize a visualização",
                "description": "Adicione ou remova gráficos — distribuição de horários de entrada, presença por departamento, tendências semanais e mais.",
            },
            4: {
                "title": "Registros de presença",
                "description": "Navegue, filtre e exporte o histórico completo de presença para qualquer período ou grupo de funcionários.",
            },
            5: {
                "title": "Solicitações de correção e horas extras",
                "description": "Os funcionários sinalizam registros de ponto incorretos — você aprova as correções com um clique. As horas extras (Conta de Horas) acompanham horas adicionais e licença compensatória.",
            },
        },
    },
    "payroll-overview": {
        "title": "Folha de Pagamento",
        "description": "Um tour guiado pelos contratos, execuções de folha de pagamento e gestão de holerites.",
        "steps": {
            1: {
                "title": "Folha de Pagamento",
                "description": "Gerencie contratos de funcionários, execute a folha de pagamento, gere holerites e administre empréstimos e reembolsos.",
            },
            2: {
                "title": "KPIs da Folha de Pagamento",
                "description": "Custo total da folha de pagamento, contratos ativos, holerites pendentes e reembolsos resumidos no topo.",
            },
            3: {
                "title": "Fluxo de holerites",
                "description": "Acompanhe os holerites por status: rascunho, confirmado, enviado e pago — durante o período de pagamento atual.",
            },
            4: {
                "title": "Contratos e componentes",
                "description": "Configure o contrato de cada funcionário com o salário base. Depois adicione auxílios (como auxílio-moradia e auxílio-transporte) e deduções (como contribuições previdenciárias e de seguro) que se aplicam automaticamente.",
            },
            5: {
                "title": "Executar a folha de pagamento",
                "description": "Gere holerites de um período de pagamento com um clique — o Horilla calcula o salário bruto, as deduções e o salário líquido automaticamente.",
            },
        },
    },
    "asset-management": {
        "title": "Gestão de Ativos",
        "description": "Um tour guiado pelo rastreamento, atribuição e histórico de ativos da empresa.",
        "steps": {
            1: {
                "title": "Gestão de Ativos",
                "description": "Rastreie todos os ativos da empresa — notebooks, telefones, veículos — e saiba exatamente quem está com cada um.",
            },
            2: {
                "title": "Visão geral de ativos",
                "description": "Principais métricas: total de ativos, alocados versus disponíveis, solicitações pendentes e ativos com devolução prevista.",
            },
            3: {
                "title": "Vencendo e com devolução prevista",
                "description": "Fique por dentro das garantias e prazos de devolução — ativos que vencem em breve aparecem aqui.",
            },
            4: {
                "title": "Alocações atuais",
                "description": "Veja quem está com cada ativo atualmente. Clique para ver o histórico completo de atribuições e registros de transferência.",
            },
            5: {
                "title": "Atribuir e gerenciar ativos",
                "description": "Use a barra lateral para adicionar categorias de ativos, criar lotes e entregar ativos aos funcionários por meio de Solicitação e Alocação.",
            },
        },
    },
    "performance-management": {
        "title": "Gestão de Desempenho",
        "description": "Um tour guiado pelos OKRs, feedback 360° e avaliações.",
        "steps": {
            1: {
                "title": "Gestão de Desempenho",
                "description": "Execute OKRs, feedback 360° e avaliações — tudo em uma plataforma de desempenho integrada.",
            },
            2: {
                "title": "Visão geral dos objetivos",
                "description": "Veja o status de todos os objetivos (no prazo, em risco, concluído) durante o período de avaliação atual.",
            },
            3: {
                "title": "Resultados-Chave",
                "description": "Aprofunde-se nos resultados-chave de cada objetivo para acompanhar o progresso detalhado e atualizar as pontuações.",
            },
            4: {
                "title": "Feedback 360°",
                "description": "Reúna feedback estruturado de colegas, subordinados e administradores. Os funcionários veem os resultados após o encerramento do período de avaliação.",
            },
            5: {
                "title": "Reuniões e pontos de bônus",
                "description": "Agende reuniões individuais e avaliações de equipe pelo menu Reuniões. Recompense o desempenho excepcional com pontos de bônus pela barra lateral.",
            },
        },
    },
    "onboarding-pipeline": {
        "title": "Integração",
        "description": "Um tour guiado pelo fluxo de integração de funcionários e gestão de tarefas.",
        "steps": {
            1: {
                "title": "Integração",
                "description": "Guie os novos contratados em seus primeiros dias: assinatura de documentos, checklists de tarefas, solicitações de equipamentos e apresentações à equipe.",
            },
            2: {
                "title": "Métricas de integração",
                "description": "Integrações ativas, tarefas concluídas, documentos assinados e tempo até a produtividade — acompanhados aqui.",
            },
            3: {
                "title": "Fluxo de etapas",
                "description": "Os novos contratados avançam por etapas estruturadas. O gráfico mostra quantos estão em cada etapa agora.",
            },
            4: {
                "title": "Tarefas e documentos",
                "description": "Atribua tarefas (por exemplo, 'Configurar notebook') e anexe documentos para assinatura (carta de oferta, termo de confidencialidade). Os funcionários concluem essas etapas pelo próprio portal.",
            },
            5: {
                "title": "Converter em funcionário",
                "description": "Depois que a integração é concluída, um clique converte o registro do candidato em um perfil completo de funcionário — sem necessidade de digitar tudo de novo.",
            },
        },
    },
    "offboarding-process": {
        "title": "Desligamento",
        "description": "Um tour guiado pelo processo de saída, cartas de demissão e acerto final.",
        "steps": {
            1: {
                "title": "Desligamento",
                "description": "Gerencie pedidos de demissão, avisos prévios e tarefas de saída para funcionários que estão deixando a empresa — tudo totalmente rastreado.",
            },
            2: {
                "title": "Métricas de desligamento",
                "description": "Saídas ativas, avisos prévios em andamento, quitações pendentes e tempo até a saída exibidos em um só olhar.",
            },
            3: {
                "title": "Fluxo de saída",
                "description": "Os funcionários que estão saindo avançam por etapas: aviso prévio cumprido, transição de responsabilidades, quitação, acerto final.",
            },
            4: {
                "title": "Acompanhamento do aviso prévio",
                "description": "Veja quem está cumprindo o aviso prévio atualmente e quantos dias restam.",
            },
            5: {
                "title": "Devolução de ativos e acerto final",
                "description": "Acompanhe quais ativos da empresa o funcionário precisa devolver. Depois que a quitação for concluída, gere o holerite final.",
            },
        },
    },
    "project-management": {
        "title": "Gestão de Projetos",
        "description": "Um tour guiado por projetos, tarefas e controle de tempo.",
        "steps": {
            1: {
                "title": "Gestão de Projetos",
                "description": "Crie projetos, atribua tarefas aos membros da equipe e controle o tempo com folhas de horas — tudo em um só lugar.",
            },
            2: {
                "title": "Saúde do projeto",
                "description": "Projetos ativos, tarefas em andamento, itens atrasados e horas registradas — os KPIs dos seus projetos em um só olhar.",
            },
            3: {
                "title": "Status das tarefas",
                "description": "Um detalhamento das tarefas por status em todos os seus projetos — a fazer, em andamento e concluída.",
            },
            4: {
                "title": "Projetos e tarefas",
                "description": "Crie um projeto, defina um prazo, adicione membros da equipe e depois divida-o em tarefas com responsáveis e datas de entrega.",
            },
            5: {
                "title": "Folhas de Horas",
                "description": "Os membros da equipe registram horas por tarefa. Os administradores veem um resumo por projeto e funcionário para faturamento ou relatórios precisos.",
            },
        },
    },
    "helpdesk-overview": {
        "title": "Central de Ajuda",
        "description": "Um tour guiado pelo sistema de chamados, Perguntas Frequentes e acompanhamento de SLA.",
        "steps": {
            1: {
                "title": "Central de Ajuda",
                "description": "Um sistema integrado de chamados de suporte — os funcionários registram problemas, o RH ou a TI os resolve, e tudo é rastreado.",
            },
            2: {
                "title": "Métricas de chamados",
                "description": "Chamados abertos, resolvidos hoje, tempo médio de resolução e cumprimento de SLA — o painel de saúde do seu suporte.",
            },
            3: {
                "title": "Gráficos de chamados",
                "description": "Visualize os chamados por status, prioridade, tipo e departamento para identificar problemas recorrentes e alocar recursos de suporte.",
            },
            4: {
                "title": "Gerenciar chamados",
                "description": "Navegue por todos os chamados abertos, atribua responsáveis, defina prioridades e responda — tudo pela lista de Chamados na barra lateral.",
            },
            5: {
                "title": "Perguntas Frequentes — reduza o volume de chamados",
                "description": "Responda antecipadamente às perguntas comuns na seção de Perguntas Frequentes. Os funcionários encontram respostas instantaneamente, reduzindo o número de chamados abertos.",
            },
        },
    },
    "settings-overview": {
        "title": "Visão Geral das Configurações",
        "description": "Um tour guiado pela área de Configurações — o primeiro lugar a visitar antes de adicionar qualquer funcionário.",
        "steps": {
            1: {
                "title": "Bem-vindo às Configurações",
                "description": "Antes de adicionar funcionários, você precisa de alguns elementos básicos. Este tour destaca cada um deles na ordem recomendada de configuração.",
            },
            2: {
                "title": "Navegação de Configurações",
                "description": "Este painel à esquerda é o seu menu de configurações. Todas as páginas de configuração estão listadas aqui — vamos percorrer primeiro as que você precisa.",
            },
            3: {
                "title": "Etapa 1 — Empresa",
                "description": "Comece com sua Empresa. Clique neste link para criar o perfil da sua empresa: nome, logotipo, endereço e moeda.",
            },
            4: {
                "title": "Etapa 2 — Departamentos",
                "description": "Depois, os Departamentos. Todo funcionário pertence a um departamento, então crie-os antes de adicionar qualquer pessoa.",
            },
            5: {
                "title": "Etapa 3 — Cargos",
                "description": "Cargos são funções nomeadas dentro de um departamento (por exemplo, Engenheiro de Software em Engenharia). Crie-os a seguir.",
            },
            6: {
                "title": "Etapa 4 — Funções",
                "description": "Funções são níveis de senioridade dentro de um cargo (por exemplo, Júnior, Sênior, Líder). Opcional, mas útil para relatórios.",
            },
            7: {
                "title": "Etapa 5 — Tipos de Trabalho",
                "description": "Tipos de Trabalho definem o regime de contratação: Integral, Parcial, Contrato, Freelancer etc.",
            },
            8: {
                "title": "Etapa 6 — Tipos de Funcionário",
                "description": "Tipos de Funcionário definem o status de vínculo: Permanente, Experiência, Estagiário etc.",
            },
            9: {
                "title": "Etapa 7 — Turnos",
                "description": "Por fim, os Turnos definem os horários de trabalho: Manhã, Tarde, Noite ou qualquer escala personalizada. Assim que isso for feito, você estará pronto para adicionar seu primeiro funcionário.",
            },
        },
    },
    "settings-company": {
        "title": "Configuração da Empresa",
        "description": "Como adicionar e configurar o perfil da sua empresa no Horilla.",
        "steps": {
            1: {
                "title": "Configurações da Empresa",
                "description": "Esta é a página de Empresa. Tudo no Horilla — funcionários, licenças, folha de pagamento — está vinculado a uma empresa, então você precisa criar uma primeiro.",
            },
            2: {
                "title": "Crie sua empresa",
                "description": "Clique neste botão Criar para adicionar sua empresa. Preencha o nome, logotipo, endereço e moeda.",
            },
            3: {
                "title": "Lista de empresas",
                "description": "Depois de salva, sua empresa aparece aqui. Você pode editar os detalhes ou adicionar mais empresas a qualquer momento.",
            },
            4: {
                "title": "Próximo — Departamentos",
                "description": "A empresa está configurada. Agora clique em Departamento no menu à esquerda para criar os departamentos aos quais seus funcionários vão pertencer.",
            },
        },
    },
    "settings-department": {
        "title": "Configuração de Departamento",
        "description": "Como criar e gerenciar departamentos para sua organização.",
        "steps": {
            1: {
                "title": "Departamentos",
                "description": "Departamentos são os agrupamentos de nível superior da sua organização: RH, Engenharia, Financeiro, Vendas etc. Todo funcionário precisa pertencer a um.",
            },
            2: {
                "title": "Crie um departamento",
                "description": "Clique em Criar, digite um nome (por exemplo, 'Engenharia') e, opcionalmente, atribua um administrador. O administrador poderá então aprovar licenças e visualizar a presença da sua equipe.",
            },
            3: {
                "title": "Seus departamentos",
                "description": "Os departamentos que você criar aparecem nesta lista. Clique na linha para editar ou excluir um deles.",
            },
            4: {
                "title": "Próximo — Cargos",
                "description": "Os departamentos estão configurados. Agora clique em Cargos no menu à esquerda para definir as funções que existem em cada departamento.",
            },
        },
    },
    "settings-job-position": {
        "title": "Configuração de Cargo",
        "description": "Como criar cargos e vinculá-los a departamentos.",
        "steps": {
            1: {
                "title": "Cargos",
                "description": "Um Cargo é uma função nomeada dentro de um departamento — por exemplo, 'Engenheiro de Software' em Engenharia, ou 'Administrador de RH' em RH. Todo perfil de funcionário exige um.",
            },
            2: {
                "title": "Crie um cargo",
                "description": "Clique em Criar. Selecione o departamento ao qual este cargo pertence e, em seguida, dê um nome a ele. Repita para cada função da sua organização.",
            },
            3: {
                "title": "Lista de cargos",
                "description": "Todos os cargos aparecem aqui. Ao adicionar um funcionário, a lista de cargos será filtrada automaticamente para mostrar apenas os cargos do departamento selecionado.",
            },
            4: {
                "title": "Próximo — Funções",
                "description": "Os cargos estão configurados. Clique em Função no menu à esquerda para adicionar níveis de senioridade (Júnior, Sênior, Líder) dentro de cada cargo.",
            },
        },
    },
    "settings-job-role": {
        "title": "Configuração de Função",
        "description": "Como criar funções dentro dos cargos.",
        "steps": {
            1: {
                "title": "Funções",
                "description": "Funções são as especializações ou níveis de senioridade dentro de um cargo. Por exemplo, o cargo 'Engenheiro de Software' pode ter as funções: Engenheiro Júnior, Engenheiro Sênior e Líder Técnico.",
            },
            2: {
                "title": "Crie uma função",
                "description": "Clique em Criar, dê um nome à função e selecione a qual cargo ela pertence. As funções são opcionais — se sua organização não usa níveis de senioridade, você pode pular esta etapa.",
            },
            3: {
                "title": "Como as funções são usadas",
                "description": "Ao adicionar ou editar um funcionário, depois de selecionar o cargo dele, você pode opcionalmente especificar sua função. As funções aparecem nos relatórios e podem ser usadas para filtrar o diretório de funcionários.",
            },
            4: {
                "title": "Próximo passo: Tipos de Trabalho",
                "description": "Depois que a estrutura organizacional estiver configurada (Empresa → Departamentos → Cargos → Funções), configure como seus funcionários trabalham. Vá em seguida para Configurações → Tipos de Trabalho.",
            },
        },
    },
    "settings-work-type": {
        "title": "Configuração de Tipo de Trabalho",
        "description": "Como configurar tipos de trabalho — integral, parcial, contrato e assim por diante.",
        "steps": {
            1: {
                "title": "Tipos de Trabalho",
                "description": "Os tipos de trabalho definem como um funcionário é contratado — Integral, Parcial, Contrato, Freelancer e assim por diante. Todo funcionário precisa ter um tipo de trabalho atribuído.",
            },
            2: {
                "title": "Crie um tipo de trabalho",
                "description": "Clique em Criar e dê um nome ao tipo de trabalho. O Horilla já vem com padrões comuns — adicione quaisquer tipos personalizados que sua empresa utilize.",
            },
            3: {
                "title": "Tipos de Trabalho Rotativos",
                "description": "Se os funcionários alternam entre modalidades de trabalho (por exemplo, alternando entre semanas presenciais e remotas), use o recurso de Tipo de Trabalho Rotativo para automatizar a escala.",
            },
            4: {
                "title": "Próximo passo: Tipos de Funcionário",
                "description": "O tipo de trabalho descreve o regime de contratação. O tipo de funcionário descreve o status de vínculo (Permanente, Experiência, Estagiário etc.). Vá em seguida para Configurações → Tipos de Funcionário.",
            },
        },
    },
    "settings-employee-type": {
        "title": "Configuração de Tipo de Funcionário",
        "description": "Como configurar tipos de funcionário — permanente, experiência, estagiário e assim por diante.",
        "steps": {
            1: {
                "title": "Tipos de Funcionário",
                "description": "Os tipos de funcionário descrevem o status de vínculo de um funcionário — Permanente, Experiência, Estagiário, Contratado e assim por diante. Todo funcionário precisa ter um tipo de funcionário atribuído.",
            },
            2: {
                "title": "Crie um tipo de funcionário",
                "description": "Clique em Criar e dê um nome ao tipo. Você pode criar quantos tipos sua política de RH exigir — por exemplo, 'Permanente', 'Experiência de 3 Meses', 'Experiência de 6 Meses', 'Estagiário'.",
            },
            3: {
                "title": "Como os tipos de funcionário são usados",
                "description": "O tipo de funcionário aparece no perfil do funcionário e pode ser usado para filtrar o diretório, gerar relatórios e aplicar diferentes políticas de licença. Por exemplo, funcionários em experiência podem não ter direito a determinados tipos de licença.",
            },
            4: {
                "title": "Próximo passo: Turnos",
                "description": "A última etapa antes de adicionar funcionários é definir os turnos de trabalho. Vá para Configurações → Turnos para criar escalas de manhã, tarde, noite ou qualquer turno personalizado.",
            },
        },
    },
    "settings-employee-shift": {
        "title": "Configuração de Turno",
        "description": "Como criar turnos de trabalho e atribuí-los aos funcionários.",
        "steps": {
            1: {
                "title": "Turnos de Trabalho",
                "description": "Os turnos definem quando seus funcionários trabalham — por exemplo, Manhã (9h–17h), Tarde (14h–22h) ou Noite (22h–6h). Todo funcionário precisa ter um turno atribuído.",
            },
            2: {
                "title": "Crie um turno",
                "description": "Clique em Criar. Dê um nome, defina o horário de início e término e configure as tolerâncias para atrasos. Repita para cada escala da sua organização.",
            },
            3: {
                "title": "Lista de turnos",
                "description": "Os turnos aparecem aqui. Cada turno também pode ter uma escala por dia, então meios períodos na sexta-feira ou horários de fim de semana diferentes são totalmente suportados.",
            },
            4: {
                "title": "Você está pronto!",
                "description": "Empresa ✓  Departamentos ✓  Cargos ✓  Funções ✓  Tipos de Trabalho ✓  Tipos de Funcionário ✓  Turnos ✓ — agora vá ao módulo de Funcionários para adicionar seu primeiro funcionário.",
            },
        },
    },
    "recruitment-dashboard": {
        "title": "Painel de Recrutamento",
        "description": "Um tour guiado pelo painel de recrutamento — KPIs, fluxo, gráficos e agenda de entrevistas.",
        "steps": {
            1: {
                "title": "Painel de Recrutamento",
                "description": "Este painel oferece uma visão em tempo real de toda a sua operação de contratação — vagas, candidatos, saúde do fluxo e agenda de entrevistas, tudo em um só lugar.",
            },
            2: {
                "title": "Cartões de KPI",
                "description": "Total de vagas, recrutamentos em andamento, candidatos contratados, taxa de conversão e taxa de aceitação de proposta — suas principais métricas de contratação atualizadas em tempo real.",
            },
            3: {
                "title": "Funil de Conversão por Etapa",
                "description": "Veja quantos candidatos avançam por cada etapa de contratação e onde ocorrem as desistências. Clique em uma barra para se aprofundar nos candidatos daquela etapa.",
            },
            4: {
                "title": "Candidatos por Etapa",
                "description": "Um detalhamento de todos os candidatos ativos nas etapas do seu fluxo — Inicial, Teste, Entrevista, Contratado e Cancelado.",
            },
            5: {
                "title": "Status da Carta de Proposta",
                "description": "Acompanhe, em um só olhar, quantas cartas de proposta estão pendentes, aceitas ou rejeitadas entre todos os candidatos.",
            },
            6: {
                "title": "Origem da Contratação",
                "description": "Entenda de onde vêm seus candidatos bem-sucedidos — formulário de inscrição, indicações, movimentação interna ou outras origens.",
            },
            7: {
                "title": "Tabela do Fluxo de Contratação",
                "description": "Um detalhamento completo de cada recrutamento ativo — mostrando a contagem de candidatos por etapa para que você identifique gargalos instantaneamente.",
            },
            8: {
                "title": "Painel de Entrevistas",
                "description": "Todas as entrevistas agendadas no período selecionado são listadas aqui — nome do candidato, etapa e horário em um só olhar.",
            },
            9: {
                "title": "Filtrar por Período",
                "description": "Use o seletor de período para focar no mês atual, no mês anterior, no trimestre ou em qualquer intervalo de datas personalizado. Todos os gráficos e KPIs são atualizados instantaneamente.",
            },
        },
    },
    "recruitment-survey": {
        "title": "Questionário de Recrutamento",
        "description": "Um tour guiado pelos modelos de questionário, banco de perguntas e como os questionários são vinculados aos recrutamentos.",
        "steps": {
            1: {
                "title": "Modelos de Questionário",
                "description": "A página de Modelos de Questionário permite criar bancos de perguntas reutilizáveis e grupos de modelos que são enviados aos candidatos durante o recrutamento. Organize suas perguntas em modelos nomeados — por exemplo, Triagem Técnica ou Adequação Cultural — e atribua-os a qualquer fluxo de recrutamento.",
            },
            2: {
                "title": "Visão Geral das Abas",
                "description": "A página é dividida em duas abas: Modelos agrupa suas perguntas sob títulos nomeados, e Perguntas contém as perguntas individuais reutilizáveis que compõem esses modelos.",
            },
            3: {
                "title": "Aba Modelos",
                "description": "A aba Modelos lista todos os seus grupos de modelos nomeados. Cada grupo em formato de acordeão mostra quais perguntas pertencem a ele e quantas são. Clique em um grupo para expandi-lo e ver suas perguntas.",
            },
            4: {
                "title": "Criar Grupo de Modelo",
                "description": "Clique no botão + na aba Modelos para criar um novo grupo de modelo. Dê um título a ele — isso se torna o nome do grupo que você vai atribuir a um fluxo de recrutamento.",
            },
            5: {
                "title": "Grupo de Modelo",
                "description": "Cada linha do acordeão é um grupo de modelo. Ela mostra o nome do grupo e a quantidade de perguntas vinculadas a ele. Expanda-o para revisar as perguntas individuais dentro dele.",
            },
            6: {
                "title": "Ações do Modelo",
                "description": "Clique no botão de três pontos (⋮) em qualquer grupo de modelo para acessar suas ações — Visualizar o questionário completo como um candidato o veria, Adicionar Perguntas do seu banco de perguntas, Editar o nome do grupo ou Excluir o grupo por completo.",
            },
            7: {
                "title": "Aba Perguntas",
                "description": "A aba Perguntas é seu banco de perguntas reutilizáveis. Cada cartão é uma pergunta — texto, múltipla escolha, avaliação ou envio de arquivo — que pode ser adicionada a qualquer grupo de modelo.",
            },
            8: {
                "title": "Criar Pergunta",
                "description": "Clique no botão + na aba Perguntas para criar uma nova pergunta individual. Defina o texto da pergunta, escolha o tipo de resposta e, opcionalmente, marque-a como obrigatória. Depois de salva, ela aparece no banco pronta para ser adicionada aos modelos.",
            },
            9: {
                "title": "Pesquisar",
                "description": "Use a caixa de pesquisa para filtrar perguntas por nome. A lista é atualizada conforme você digita — útil quando seu banco de perguntas cresce muito e você precisa localizar uma pergunta específica rapidamente.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista de perguntas por tipo de resposta ou recrutamento. Use isso para revisar todas as perguntas de um determinado tipo ou para ver quais perguntas estão vinculadas a um fluxo de recrutamento específico.",
            },
        },
    },
    "candidate-view-tour": {
        "title": "Candidatos",
        "description": "Um tour guiado pela lista de candidatos — pesquisa, filtro, visualizações e gestão de candidatos.",
        "steps": {
            1: {
                "title": "Candidatos",
                "description": "A página de Candidatos é uma visão consolidada de todos os inscritos em todos os seus recrutamentos ativos. Pesquise, filtre, agrupe e gerencie candidatos — independentemente do fluxo ou etapa em que estejam atualmente.",
            },
            2: {
                "title": "Lista de Candidatos",
                "description": "A área principal lista todos os candidatos com nome, e-mail, telefone, avaliação, recrutamento e cargo. Clique em qualquer linha para abrir o perfil completo do candidato — currículo, histórico de entrevistas, respostas do questionário e status da carta de proposta.",
            },
            3: {
                "title": "Criar Candidato",
                "description": "Clique em Criar para adicionar manualmente um novo candidato. Preencha os dados pessoais, atribua um recrutamento e uma etapa inicial, e o candidato aparece imediatamente no fluxo.",
            },
            4: {
                "title": "Menu de Ações",
                "description": "O menu Ações oferece operações em massa — Exportar dados dos candidatos para uma planilha, enviar E-mail em Massa, criar uma Solicitação de Documento, Arquivar ou Desarquivar os candidatos selecionados e Excluir em massa. Selecione os candidatos usando as caixas de seleção primeiro.",
            },
            5: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Alterne entre a visualização em Lista para uma tabela detalhada e a visualização em Cartão para uma grade visual. Use os ícones de alternância ao lado da barra de pesquisa para mudar o layout. Sua última visualização usada é lembrada.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar candidatos por nome. A lista é atualizada conforme você digita — útil quando você tem um grande número de candidatos e precisa localizar alguém rapidamente.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por recrutamento, etapa, status de contratação, origem, departamento, cargo, país e mais. Você também pode usar Agrupar Por dentro do filtro para organizar os resultados por recrutamento, etapa ou outros campos.",
            },
        },
    },
    "scheduled-interviews-tour": {
        "title": "Entrevistas Agendadas",
        "description": "Um tour guiado pela lista de entrevistas agendadas — status, filtro, agendamento e gestão de entrevistas.",
        "steps": {
            1: {
                "title": "Entrevistas Agendadas",
                "description": "A página de Entrevistas Agendadas lista todas as entrevistas de todos os recrutamentos em um só lugar. Cada linha mostra o candidato, os entrevistadores designados, data, horário e um status em tempo real — Próxima, Entrevista Hoje, Concluída ou Expirada — calculado automaticamente.",
            },
            2: {
                "title": "Lista de Entrevistas",
                "description": "Cada linha mostra o nome do candidato, os entrevistadores, a data e horário agendados, a descrição e o status atual. Clique em qualquer linha para abrir o detalhe completo da entrevista — atualizar o resultado, adicionar observações ou reagendar a partir dali.",
            },
            3: {
                "title": "Agendar uma Entrevista",
                "description": "Clique em Criar para agendar uma nova entrevista. Selecione o candidato, atribua um ou mais entrevistadores, defina a data e o horário, e adicione uma descrição ou pauta. A entrevista aparece imediatamente na lista.",
            },
            4: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Entrevistador, Horário da Entrevista, Descrição ou Status — para focar nos dados que você precisa.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar entrevistas por nome do candidato ou entrevistador. A lista é atualizada conforme você digita — útil para encontrar uma entrevista específica em uma agenda cheia.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por candidato, entrevistador, intervalo de datas da entrevista ou status. Use os filtros de data para ver todas as entrevistas previstas para hoje ou para esta semana em um só olhar.",
            },
        },
    },
    "recruitment-list-tour": {
        "title": "Recrutamento",
        "description": "Um tour guiado pela lista de recrutamentos — criação, gestão e compartilhamento de processos de recrutamento.",
        "steps": {
            1: {
                "title": "Recrutamento",
                "description": "A página de Recrutamento lista todos os seus processos de contratação. Cada linha é um recrutamento — mostrando seu título, administradores designados, cargos em aberto, meta de vagas, total de contratações até o momento, datas de início e término, e se está aberto ou encerrado.",
            },
            2: {
                "title": "Lista de Recrutamentos",
                "description": "Cada linha representa um processo de recrutamento. Clique em uma linha para abrir seu painel de detalhes — onde você pode ver o registro completo, editar as configurações ou acessar o fluxo daquela vaga. Uma borda esquerda colorida indica se está aberto ou encerrado.",
            },
            3: {
                "title": "Criar Recrutamento",
                "description": "Clique em Criar para iniciar um novo processo de recrutamento. Defina o título, atribua administradores de recrutamento, adicione cargos, defina o número de vagas, anexe modelos de questionário e defina as datas de início e término.",
            },
            4: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Administradores, Vagas Abertas, Número de Vagas, Total de Contratações, Data de Início ou Data de Término — para adaptar a visualização às suas necessidades.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar recrutamentos por título. A lista é atualizada conforme você digita — útil quando você gerencia muitas vagas abertas e encerradas e precisa localizar uma rapidamente.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por cargo, departamento, empresa, status de aberto ou encerrado, e intervalo de data de início ou término. Use o filtro de encerrados para revisar dados históricos de recrutamento.",
            },
        },
    },
    "recruitment-stage-tour": {
        "title": "Etapas",
        "description": "Um tour guiado pelas etapas de recrutamento — tipos, agrupamento por recrutamento, criação e gestão das etapas do fluxo.",
        "steps": {
            1: {
                "title": "Etapas",
                "description": "As etapas definem os passos pelos quais os candidatos avançam em um fluxo de recrutamento — Inicial, Teste, Entrevista, Contratado e Cancelado. Esta página lista todas as etapas ativas com seu recrutamento, administradores designados e tipo. A ordem aqui determina a sequência das colunas no quadro kanban do fluxo.",
            },
            2: {
                "title": "Lista de Etapas",
                "description": "Cada linha mostra uma etapa com seu título, administradores designados e tipo. Clique em qualquer linha para abrir o painel de detalhes onde você pode editar o nome da etapa, reatribuir administradores, alterar seu tipo ou excluí-la.",
            },
            3: {
                "title": "Criar Etapa",
                "description": "Clique em Criar para adicionar uma nova etapa. Dê um título a ela, selecione o tipo de etapa — Inicial, Teste, Entrevista, Contratado ou Cancelado —, atribua administradores da etapa e vincule-a a um recrutamento. A etapa aparece imediatamente no fluxo daquele recrutamento.",
            },
            4: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Título, Administradores ou Tipo — para focar nas informações que você precisa.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar etapas por nome. A lista é atualizada conforme você digita — útil quando há muitas etapas em vários recrutamentos e você precisa encontrar uma rapidamente.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por recrutamento, tipo de etapa (Inicial, Teste, Entrevista, Contratado, Cancelado) ou administrador da etapa. Use a opção Agrupar Por dentro do filtro para organizar as etapas sob seu recrutamento.",
            },
        },
    },
    "skill-zone-tour": {
        "title": "Zona de Habilidade",
        "description": "Um tour guiado pela Zona de Habilidade — bancos de talentos para armazenar candidatos fortes para futuros recrutamentos.",
        "steps": {
            1: {
                "title": "Zona de Habilidade",
                "description": "A Zona de Habilidade é um banco de talentos — um lugar para guardar candidatos fortes que não foram contratados nesta vaga, mas devem ser considerados para futuras oportunidades. Organizada por habilidade ou função, não por recrutamento.",
            },
            2: {
                "title": "Grupos da Zona de Habilidade",
                "description": "Cada zona de habilidade é um grupo nomeado — por exemplo, 'Desenvolvedores Python' ou 'Talentos de Vendas'. Clique em qualquer linha de grupo para expandi-la e ver os candidatos armazenados dentro dela.",
            },
            3: {
                "title": "Candidatos Dentro de uma Zona de Habilidade",
                "description": "As linhas expandidas mostram o nome de cada candidato, o motivo pelo qual foi adicionado, a data de adição e um link para o currículo. Clique na linha de um candidato para abrir seu perfil completo.",
            },
            4: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
            6: {
                "title": "Criar uma Zona de Habilidade",
                "description": "Clique em Criar para adicionar um novo grupo de zona de habilidade — dê a ele um título e uma descrição que reflitam o conjunto de habilidades ou a função para a qual você quer reunir candidatos.",
            },
            7: {
                "title": "Adicionar Candidatos a uma Zona de Habilidade",
                "description": "Use o ícone de pessoa+ em qualquer linha de zona de habilidade para adicionar um candidato àquele banco. Você também pode adicionar candidatos diretamente pelo fluxo ao rejeitá-los ou arquivá-los.",
            },
            8: {
                "title": "Editar e Arquivar Zonas de Habilidade",
                "description": "Use o ícone de edição para renomear uma zona de habilidade, o ícone de arquivo para ocultá-la sem excluí-la, e o ícone de lixeira para removê-la permanentemente.",
            },
        },
    },
    "onboarding-pipeline-tour": {
        "title": "Fluxo de Integração",
        "description": "Um tour guiado pelo fluxo de integração — etapas, cartões de candidatos, tarefas e conversão em funcionário.",
        "steps": {
            1: {
                "title": "Fluxo de Integração",
                "description": "O Fluxo de Integração guia os novos contratados desde a aceitação da proposta até se tornarem funcionários totalmente ativos. Cada recrutamento ativo aparece como uma aba, e dentro de cada aba os candidatos avançam por etapas de integração personalizáveis representadas como colunas.",
            },
            2: {
                "title": "Quadro do Fluxo",
                "description": "O quadro do fluxo mostra todos os recrutamentos de integração ativos como abas. Alterne entre a visualização em Lista e a visualização em Cartão (kanban) usando os botões de alternância para mudar como as colunas de etapas são exibidas.",
            },
            3: {
                "title": "Abas de Recrutamento",
                "description": "Cada aba representa um recrutamento ativo cujos candidatos estão sendo integrados. Clique em uma aba para focar naquele fluxo — suas colunas de etapas de integração e cartões de candidatos são carregados abaixo. O indicador mostra quantas etapas aquele recrutamento tem.",
            },
            4: {
                "title": "Ações de Etapa",
                "description": "Clique nos três pontos (⋮) em qualquer aba de recrutamento para acessar a gestão de etapas — Adicionar Etapa para criar um novo passo de integração, ou Gerenciar Ordem das Etapas para reordenar as colunas no fluxo.",
            },
            5: {
                "title": "Coluna de Etapa",
                "description": "Cada coluna é uma etapa de integração — como Assinatura de Documentos, Configuração de Equipamentos ou Ambientação. Na visualização em lista, clique no cabeçalho para recolher ou expandir a etapa. Na visualização em cartão, os cartões de candidatos mostram o progresso das tarefas e a data de admissão em um só olhar.",
            },
            6: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use a alternância de visualização para trocar entre a visualização em Lista — uma tabela de candidatos por etapa — e a visualização em Cartão — um quadro kanban onde você pode arrastar candidatos entre etapas. Ambas as visualizações são atualizadas em tempo real.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar candidatos por nome em todas as etapas de integração. O fluxo é atualizado conforme você digita — útil ao gerenciar um grande grupo de novos contratados.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir o fluxo por recrutamento, departamento, data de admissão ou etapa de integração. Use isso para focar nos novos contratados de uma equipe específica ou revisar candidatos em uma etapa específica.",
            },
        },
    },
    "onboarding-hired-candidates-tour": {
        "title": "Candidatos Contratados",
        "description": "Um tour guiado pela lista de candidatos contratados em integração — links de portal, datas de admissão, cartas de proposta e conversão em funcionário.",
        "steps": {
            1: {
                "title": "Candidatos Contratados",
                "description": "A página de Candidatos Contratados lista todos os candidatos marcados como contratados e que estão atualmente passando pela integração. A partir daqui você pode gerenciar a data de admissão, o período de experiência, o acesso ao portal e a carta de proposta — tudo em um só lugar.",
            },
            2: {
                "title": "Lista de Candidatos",
                "description": "Cada linha mostra um candidato contratado com nome, e-mail, data de admissão, data final da experiência, cargo, recrutamento e status da carta de proposta. Clique em qualquer linha para abrir o perfil completo de integração do candidato.",
            },
            3: {
                "title": "Criar Candidato Contratado",
                "description": "Clique em Criar para adicionar manualmente um candidato contratado à lista de integração. Defina seus dados pessoais, atribua um recrutamento e uma data de admissão para que apareça imediatamente no fluxo.",
            },
            4: {
                "title": "Enviar Link do Portal",
                "description": "Clique no ícone de link do portal em qualquer linha de candidato para enviar o link do portal de autoatendimento de integração. Eles podem fazer login para concluir tarefas, enviar documentos e acompanhar o próprio progresso de integração sem envolver o RH em cada etapa.",
            },
            5: {
                "title": "Iniciar Integração",
                "description": "Cada linha de candidato tem dois ícones de ação — o ícone + (Iniciar Integração) adiciona o candidato ao fluxo de integração para que tarefas e etapas possam ser atribuídas. Depois de adicionado, o ícone muda para a cor azul-petróleo indicando que ele já está no fluxo.",
            },
            6: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — E-mail, Data de Admissão, Fim da Experiência, Carta de Proposta e mais — para focar nos dados relevantes ao seu fluxo de trabalho.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar candidatos contratados por nome. A lista é atualizada conforme você digita — útil ao gerenciar um grande grupo de integração e precisar localizar alguém rapidamente.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por recrutamento, cargo, intervalo de data de admissão, período de experiência, status de envio do portal ou status da carta de proposta. Use Agrupar Por para organizar os candidatos por recrutamento ou departamento.",
            },
        },
    },
    "employee-profile-tour": {
        "title": "Perfil do Funcionário",
        "description": "Um tour guiado pelo seu perfil de funcionário — foto, abas, licença, presença, documentos e folha de pagamento.",
        "steps": {
            1: {
                "title": "Seu Perfil de Funcionário",
                "description": "Este é o seu perfil de funcionário pessoal — um único lugar onde você pode ver e gerenciar todas as suas informações de trabalho, saldos de licença, registros de presença, documentos e mais.",
            },
            2: {
                "title": "Foto de Perfil e Informações Básicas",
                "description": "Sua foto de perfil, nome, e-mail, telefone e gênero são exibidos no topo. Essas informações são obtidas do seu registro de funcionário e são visíveis para seu administrador e o RH.",
            },
            3: {
                "title": "Abas do Perfil",
                "description": "Use as abas para navegar entre as diferentes seções do seu perfil — Sobre, Tipo de Trabalho e Turno, Presença, Licença, Folha de Pagamento, Documentos, Desempenho e mais.",
            },
            4: {
                "title": "Aba Sobre",
                "description": "A aba Sobre mostra seus dados pessoais, informações de trabalho, contatos de emergência e dados bancários. Clique em qualquer campo para editá-lo diretamente, se você tiver permissão.",
            },
            5: {
                "title": "Menu de Ações",
                "description": "Clique no ícone de engrenagem para acessar as ações do perfil — redefinir sua senha, bloquear ou desbloquear o acesso à conta e outras ações administrativas, dependendo das suas permissões.",
            },
            6: {
                "title": "Licença e Presença",
                "description": "Acesse a aba Licença para ver seus saldos de licença, histórico de solicitações e aprovações. A aba Presença mostra seus registros de entrada/saída e quaisquer sinalizações de atraso ou saída antecipada.",
            },
            7: {
                "title": "Documentos e Folha de Pagamento",
                "description": "A aba Documentos contém seus arquivos enviados e documentos compartilhados pelo RH. A aba Folha de Pagamento mostra seus holerites, auxílios, deduções e pontos de bônus — tudo em um só lugar.",
            },
        },
    },
    "document-requests-tour": {
        "title": "Solicitações de Documento",
        "description": "Um tour guiado pelas solicitações de documento — criação de solicitações, acompanhamento de envios e aprovação ou rejeição de documentos enviados.",
        "steps": {
            1: {
                "title": "Solicitações de Documento",
                "description": "Esta página gerencia solicitações de documento feitas aos funcionários. O RH ou os administradores podem solicitar documentos específicos aos funcionários e acompanhar se foram enviados, aprovados ou rejeitados.",
            },
            2: {
                "title": "Fluxo de Solicitações",
                "description": "As solicitações de documento são agrupadas por tipo de solicitação. Cada grupo mostra quantos documentos foram enviados em relação ao total solicitado. Clique no cabeçalho de um grupo para expandi-lo e ver os registros individuais dos funcionários.",
            },
            3: {
                "title": "Cabeçalho do Grupo de Solicitação",
                "description": "Cada cabeçalho mostra o nome da solicitação de documento e o progresso de envio. Clique no cabeçalho para expandir ou recolher as linhas de funcionários abaixo dele. O botão de três pontos (⋮) à direita permite Editar ou Excluir a solicitação.",
            },
            4: {
                "title": "Editar ou Excluir uma Solicitação",
                "description": "Clique nos três pontos (⋮) em um grupo de solicitação para Editar seu título e descrição, ou Excluir a solicitação por completo. Excluir uma solicitação remove todos os registros de documentos de funcionários associados.",
            },
            5: {
                "title": "Criar Solicitação de Documento",
                "description": "Clique em Criar para fazer uma nova solicitação de documento. Especifique o tipo de documento e adicione uma descrição do que os funcionários precisam enviar. A solicitação aparece imediatamente como um novo grupo no fluxo.",
            },
            6: {
                "title": "Aprovar ou Rejeitar em Massa",
                "description": "Clique em Ações para aprovar ou rejeitar em massa vários envios de documentos selecionados de uma só vez. Selecione as linhas de funcionários usando as caixas de seleção primeiro e depois escolha Aprovar em Massa ou Rejeitar em Massa no menu.",
            },
            7: {
                "title": "Aprovar e Rejeitar Envios Individuais",
                "description": "Depois que um funcionário envia um documento, expanda o grupo de solicitação dele para ver a linha. Um visto verde significa aprovado, um alerta vermelho significa rejeitado, um ícone de arquivo significa enviado mas ainda não revisado. Use os botões de aprovar ou rejeitar na linha para agir sobre ele.",
            },
            8: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar solicitações de documento por nome do funcionário. O fluxo é atualizado conforme você digita — útil ao gerenciar solicitações em uma grande equipe.",
            },
            9: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir as solicitações por departamento, cargo, status do documento ou tipo de solicitação. Use isso para focar em envios pendentes ou documentos aguardando aprovação.",
            },
        },
    },
    "shift-requests-tour": {
        "title": "Solicitações de Turno",
        "description": "Um tour guiado pelas solicitações de turno — criação, aprovação, rejeição e acompanhamento de solicitações de mudança de turno dos funcionários.",
        "steps": {
            1: {
                "title": "Solicitações de Turno",
                "description": "Esta página gerencia as solicitações dos funcionários para alterar o turno de trabalho atribuído. Os administradores podem revisar, aprovar ou rejeitar as solicitações, e os funcionários podem acompanhar o status dos próprios envios.",
            },
            2: {
                "title": "Aba Solicitações de Turno",
                "description": "A aba Solicitações de Turno lista todas as solicitações feitas pelos funcionários para alterar o turno atribuído. Cada linha mostra o funcionário, seu turno atual, o turno solicitado, o intervalo de datas e o status de aprovação atual.",
            },
            3: {
                "title": "Aba Turnos Alocados",
                "description": "A aba Solicitações de Turno Alocado mostra as alocações de turno que um administrador atribuiu diretamente aos funcionários — sem que uma solicitação precise ser feita pelo funcionário.",
            },
            4: {
                "title": "Lista de Solicitações",
                "description": "Cada linha mostra o nome do funcionário, seu turno atual, o turno que ele solicitou, o intervalo de datas solicitado e o status de aprovação atual — Solicitado (laranja), Aprovado (verde) ou Cancelado (vermelho).",
            },
            5: {
                "title": "Criar Solicitação de Turno",
                "description": "Clique em Criar para fazer uma nova solicitação de turno. Selecione o funcionário, o turno que ele está solicitando e a data a partir da qual a mudança deve entrar em vigor.",
            },
            6: {
                "title": "Ações",
                "description": "Clique em Ações para aprovar solicitações em massa, rejeitar solicitações em massa, exportar a lista para uma planilha ou excluir os registros selecionados. Selecione as linhas usando as caixas de seleção primeiro.",
            },
            7: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Turno Solicitado, Turno Atual, Data Solicitada, Solicitado Até, Status, Descrição e mais.",
            },
            8: {
                "title": "Aprovar e Rejeitar",
                "description": "Clique no ícone de aprovar ou rejeitar em qualquer linha de solicitação para agir sobre ela individualmente. As solicitações aprovadas atualizam automaticamente o turno do funcionário. As solicitações rejeitadas notificam o funcionário com um motivo, se houver.",
            },
            9: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar solicitações de turno por nome do funcionário. A lista é atualizada conforme você digita — útil ao gerenciar um grande número de solicitações pendentes.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por funcionário, turno, departamento, intervalo de datas ou status de aprovação. Use Agrupar Por para organizar as solicitações por funcionário, turno solicitado ou turno atual.",
            },
        },
    },
    "work-type-requests-tour": {
        "title": "Solicitações de Tipo de Trabalho",
        "description": "Um tour guiado pelas solicitações de tipo de trabalho — criação, aprovação, rejeição e acompanhamento de solicitações de mudança de tipo de trabalho dos funcionários.",
        "steps": {
            1: {
                "title": "Solicitações de Tipo de Trabalho",
                "description": "Esta página gerencia as solicitações dos funcionários para alterar o tipo de trabalho atribuído — por exemplo, mudar de presencial para remoto ou para meio período. Os administradores podem revisar e aprovar ou rejeitar cada solicitação.",
            },
            2: {
                "title": "Lista de Solicitações",
                "description": "Cada linha mostra o nome do funcionário, seu tipo de trabalho atual, o tipo de trabalho que ele solicitou, o intervalo de datas e o status de aprovação atual — Solicitado (laranja), Aprovado (verde) ou Rejeitado (vermelho).",
            },
            3: {
                "title": "Criar Solicitação de Tipo de Trabalho",
                "description": "Clique em Criar para fazer uma nova solicitação de tipo de trabalho. Selecione o funcionário, escolha o tipo de trabalho solicitado e defina a data a partir da qual a mudança deve entrar em vigor.",
            },
            4: {
                "title": "Ações",
                "description": "Clique em Ações para aprovar solicitações em massa, rejeitar solicitações em massa, exportar a lista para uma planilha ou excluir os registros selecionados. Selecione as linhas usando as caixas de seleção primeiro.",
            },
            5: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Tipo de Trabalho Solicitado, Tipo de Trabalho Atual, Data Solicitada, Solicitado Até, Status e Descrição.",
            },
            6: {
                "title": "Aprovar e Rejeitar",
                "description": "Use a ação de aprovar ou rejeitar em uma linha de solicitação para agir sobre ela individualmente. As solicitações aprovadas atualizam automaticamente o tipo de trabalho do funcionário a partir da data efetiva.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar solicitações de tipo de trabalho por nome do funcionário. A lista é atualizada conforme você digita — útil ao gerenciar um grande número de solicitações pendentes.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por funcionário, tipo de trabalho, departamento, intervalo de datas ou status de aprovação. Use Agrupar Por para organizar as solicitações por funcionário, tipo de trabalho ou departamento.",
            },
        },
    },
    "rotating-shift-assign-tour": {
        "title": "Atribuição de Turno Rotativo",
        "description": "Um tour guiado pelas atribuições de turno rotativo — atribuindo, editando, arquivando e acompanhando rotações automáticas de turno para os funcionários.",
        "steps": {
            1: {
                "title": "Atribuição de Turno Rotativo",
                "description": "Esta página gerencia as atribuições de turno rotativo dos funcionários. Um turno rotativo alterna automaticamente um funcionário por uma sequência de turnos — por exemplo, alternando entre manhã e tarde — com base em uma escala que você define.",
            },
            2: {
                "title": "Lista de Atribuições",
                "description": "Cada linha mostra a atribuição de turno rotativo ativa de um funcionário — o título do turno, a escala de rotação (diária, semanal ou mensal), a data de início, o turno atual e a data da próxima troca automática.",
            },
            3: {
                "title": "Atribuir Turno Rotativo",
                "description": "Clique em Atribuir para vincular um turno rotativo a um ou mais funcionários. Escolha o padrão de turno rotativo, defina a data de início, e o sistema cuidará de todas as rotações futuras automaticamente.",
            },
            4: {
                "title": "Ações",
                "description": "Clique em Ações para arquivar, desarquivar ou excluir em massa as atribuições selecionadas. Use Importar para enviar atribuições em massa a partir de uma planilha, ou Exportar para baixar a lista atual.",
            },
            5: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Turno Rotativo, Baseado Em, Data de Início, Turno Atual, Próxima Troca e Próximo Turno.",
            },
            6: {
                "title": "Ações da Linha",
                "description": "Cada linha tem ícones de ação para editar a atribuição, duplicá-la para outro funcionário, ou arquivá-la para desativar a rotação sem perder o histórico. Atribuições arquivadas podem ser restauradas pelo menu Ações.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar atribuições por nome do funcionário. A lista é atualizada conforme você digita — útil ao gerenciar turnos rotativos em uma grande equipe.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por funcionário, turno rotativo, departamento, função ou administrador responsável. Use Agrupar Por para reorganizar a tabela por turno, departamento ou qualquer outro campo.",
            },
        },
    },
    "rotating-work-type-assign-tour": {
        "title": "Atribuição de Tipo de Trabalho Rotativo",
        "description": "Um tour guiado pelas atribuições de tipo de trabalho rotativo — atribuindo, editando, arquivando e acompanhando rotações automáticas de tipo de trabalho para os funcionários.",
        "steps": {
            1: {
                "title": "Atribuição de Tipo de Trabalho Rotativo",
                "description": "Esta página gerencia as atribuições de tipo de trabalho rotativo dos funcionários. Um tipo de trabalho rotativo alterna automaticamente um funcionário por uma sequência de tipos de trabalho — por exemplo, alternando entre presencial e remoto — com base em uma escala que você define.",
            },
            2: {
                "title": "Lista de Atribuições",
                "description": "Cada linha mostra a atribuição de tipo de trabalho rotativo ativa de um funcionário — o título do tipo de trabalho, a escala de rotação (diária, semanal ou mensal), a data de início, o tipo de trabalho atual e a data da próxima troca automática.",
            },
            3: {
                "title": "Atribuir Tipo de Trabalho Rotativo",
                "description": "Clique em Atribuir para vincular um tipo de trabalho rotativo a um ou mais funcionários. Escolha o padrão de rotação e defina a data de início — o sistema cuida de todas as trocas futuras automaticamente.",
            },
            4: {
                "title": "Ações",
                "description": "Clique em Ações para arquivar, desarquivar ou excluir em massa as atribuições selecionadas. Use Importar para enviar atribuições em massa a partir de uma planilha, ou Exportar para baixar a lista atual.",
            },
            5: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Tipo de Trabalho Rotativo, Baseado Em, Data de Início, Tipo de Trabalho Atual, Próxima Troca e Próximo Tipo de Trabalho.",
            },
            6: {
                "title": "Ações da Linha",
                "description": "Cada linha tem ícones de ação para editar a atribuição, duplicá-la para outro funcionário, ou arquivá-la para desativar a rotação sem perder o histórico. Atribuições arquivadas podem ser restauradas pelo menu Ações.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar atribuições por nome do funcionário. A lista é atualizada conforme você digita — útil ao gerenciar tipos de trabalho rotativos em uma grande equipe.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por funcionário, tipo de trabalho rotativo, departamento, função ou administrador responsável. Use Agrupar Por para reorganizar a tabela por tipo de trabalho, departamento ou qualquer outro campo.",
            },
        },
    },
    "roster-planner-tour": {
        "title": "Planejador de Escalas",
        "description": "Um tour guiado pelo Planejador de Escalas — agendando turnos na grade, publicando a escala e importando escalas em massa.",
        "steps": {
            1: {
                "title": "Planejador de Escalas",
                "description": "O Planejador de Escalas permite agendar os turnos dos funcionários em um período em uma grade visual. Você pode atribuir turnos a funcionários individuais para cada dia e depois publicar a escala para que os funcionários possam vê-la.",
            },
            2: {
                "title": "Filtrar por Departamento e Período",
                "description": "Use a lista de departamentos e os seletores de data para controlar quais funcionários e qual período são exibidos na grade. Clique no botão de pesquisa para recarregar a escala com os filtros selecionados.",
            },
            3: {
                "title": "Grade da Escala",
                "description": "A grade mostra uma linha por funcionário e uma coluna por dia no período selecionado. Cada célula pode conter uma atribuição de turno. A coluna do dia de hoje é destacada para referência rápida.",
            },
            4: {
                "title": "Atribuindo Turnos",
                "description": "Clique em qualquer célula vazia da grade para atribuir um turno a esse funcionário naquele dia. Clique em uma atribuição existente para editá-la ou removê-la. As células podem conter vários turnos, se necessário.",
            },
            5: {
                "title": "Publicar a Escala",
                "description": "Clique em Publicar para tornar os turnos agendados visíveis aos funcionários. Você pode publicar para todos os funcionários ou selecionar alguns específicos. Os funcionários podem ver sua escala publicada a partir do próprio painel.",
            },
            6: {
                "title": "Importar Escala",
                "description": "Clique em Importar para enviar uma planilha de escala já preenchida — útil para agendar grandes equipes em massa. Baixe primeiro o modelo na caixa de diálogo de importação para garantir o formato correto.",
            },
            7: {
                "title": "Selecionar e Publicar em Massa",
                "description": "Use o botão Selecionar na grade para escolher vários funcionários de uma vez e depois use Publicar para enviar a escala apenas para esses funcionários — útil quando você só precisa notificar um subconjunto da sua equipe.",
            },
        },
    },
    "disciplinary-actions-tour": {
        "title": "Ações Disciplinares",
        "description": "Um tour guiado pelas ações disciplinares — registrando, revisando e gerenciando medidas disciplinares formais para os funcionários.",
        "steps": {
            1: {
                "title": "Ações Disciplinares",
                "description": "Esta página registra e gerencia as ações disciplinares tomadas contra os funcionários — advertências, suspensões, demissões e outras ações formais. Cada registro é vinculado ao funcionário e inclui o tipo de ação, a data e detalhes de apoio.",
            },
            2: {
                "title": "Lista de Ações",
                "description": "Cada linha mostra o nome do funcionário, o tipo de ação disciplinar tomada, a data da ação, se o login está bloqueado, quaisquer anexos e uma descrição. Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Criar Ação Disciplinar",
                "description": "Clique em Criar para registrar uma nova ação disciplinar. Selecione o funcionário, escolha o tipo de ação, defina a data, opcionalmente bloqueie o login dele e anexe quaisquer documentos de apoio, como cartas de advertência.",
            },
            4: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Ação Tomada, Bloqueio de Login, Data da Ação, Anexos e Descrição.",
            },
            5: {
                "title": "Ações da Linha",
                "description": "Cada linha tem ícones de ação para editar o registro, duplicá-lo para outro funcionário ou excluí-lo. Clique na própria linha para abrir a visualização completa de detalhes, incluindo observações de acompanhamento e arquivos anexados.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar registros disciplinares por nome do funcionário. A lista é atualizada conforme você digita — útil ao revisar o histórico de um funcionário específico.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por tipo de ação, data da ação, departamento, empresa ou administrador responsável. Use isso para auditar registros disciplinares em uma equipe ou período.",
            },
        },
    },
    "policies-tour": {
        "title": "Políticas",
        "description": "Um tour guiado pela página de Políticas — criando, gerenciando e compartilhando documentos de política de RH com os funcionários.",
        "steps": {
            1: {
                "title": "Políticas",
                "description": "Esta página armazena e gerencia as políticas de RH da sua organização — como política de licenças, código de conduta, diretrizes de trabalho remoto e mais. As políticas podem ser compartilhadas com todos os funcionários ou restritas a grupos específicos.",
            },
            2: {
                "title": "Cartões de Política",
                "description": "Cada cartão representa um documento de política. Um ponto verde significa que a política é visível para todos os funcionários; um ponto vermelho significa que é restrita. Clique em Ver Política em qualquer cartão para ler o conteúdo completo.",
            },
            3: {
                "title": "Criar uma Política",
                "description": "Clique em Criar para adicionar uma nova política. Dê um título a ela, escreva ou cole o conteúdo, anexe quaisquer documentos relacionados, como PDFs ou arquivos do Word, e escolha se ela deve ser visível para todos os funcionários ou apenas para alguns específicos.",
            },
            4: {
                "title": "Controle de Visibilidade",
                "description": "Cada cartão de política mostra um ponto colorido — verde significa que todos os funcionários podem vê-la pelo próprio portal de autoatendimento, vermelho significa que é restrita. Atualize a visibilidade a qualquer momento editando a política.",
            },
            5: {
                "title": "Editar e Excluir",
                "description": "Cada cartão tem um ícone de edição para atualizar o conteúdo, o título ou a visibilidade da política, e um ícone de exclusão para removê-la permanentemente. As alterações têm efeito imediato para todos os funcionários que podem ver a política.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar políticas por título. Os cartões são atualizados conforme você digita — útil quando você tem muitas políticas e precisa localizar uma rapidamente.",
            },
        },
    },
    "attendances-tour": {
        "title": "Presenças",
        "description": "Um tour guiado pela página de Presenças — revisando registros, validando entradas, aprovando horas extras e importando dados de presença em massa.",
        "steps": {
            1: {
                "title": "Presenças",
                "description": "Esta página registra cada evento de entrada e saída dos seus funcionários. Você pode revisar os registros de presença, validá-los, acompanhar as horas extras e ver quais registros já foram aprovados — tudo em um só lugar.",
            },
            2: {
                "title": "Registros de Presença",
                "description": "A lista mostra cada registro de presença com o nome do funcionário, horário de entrada, horário de saída, horas trabalhadas e status de validação atual. Clique em qualquer linha para abrir a visualização completa de detalhes daquele registro.",
            },
            3: {
                "title": "Abas — Validar, Horas Extras e Validadas",
                "description": "Use as abas para alternar entre visualizações: Presenças a Validar mostra os registros pendentes de aprovação, Presenças com Horas Extras mostra os registros de horas extras aguardando aprovação, e Presenças Validadas mostra todos os registros aprovados.",
            },
            4: {
                "title": "Criar Presença",
                "description": "Clique em Criar para adicionar manualmente um registro de presença — útil para corrigir entradas perdidas ou adicionar registros de funcionários que trabalham fora do sistema. Preencha o funcionário, a data e os horários de entrada e saída.",
            },
            5: {
                "title": "Importar Presença",
                "description": "Use Ações → Importar para enviar uma planilha de registros de presença em massa. Baixe o modelo na caixa de diálogo de importação para garantir que seu arquivo use o formato de coluna correto.",
            },
            6: {
                "title": "Presenças a Validar",
                "description": "Clique na aba Presenças a Validar para revisar os registros pendentes. Você pode aprovar entradas individuais ou selecionar várias linhas e usar o botão Validar para aprová-las em massa em uma única ação.",
            },
            7: {
                "title": "Presenças com Horas Extras",
                "description": "Acesse a aba Presenças com Horas Extras para ver os registros de horas extras. Revise cada registro e use Aprovar Horas Extras para confirmar as horas extras, que serão então incluídas nos cálculos da folha de pagamento.",
            },
            8: {
                "title": "Presenças Validadas",
                "description": "A aba Presenças Validadas mostra todos os registros que já foram aprovados. Use esta visualização para auditar entradas aprovadas ou exportar um relatório de presença validada.",
            },
            9: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "attendance-requests-tour": {
        "title": "Solicitações de Presença",
        "description": "Um tour guiado pela página de Solicitações de Presença — revisando, aprovando e gerenciando solicitações de correção de presença dos funcionários.",
        "steps": {
            1: {
                "title": "Solicitações de Presença",
                "description": "Esta página gerencia as solicitações dos funcionários para corrigir ou adicionar registros de presença. Os funcionários podem abrir uma solicitação quando perdem uma entrada ou precisam ajustar os detalhes de presença. Os administradores revisam e aprovam ou rejeitam essas solicitações aqui.",
            },
            2: {
                "title": "Aba Presenças Solicitadas",
                "description": "A aba Presenças Solicitadas mostra todas as solicitações de correção pendentes enviadas pelos funcionários. Cada linha exibe o funcionário, os horários de entrada e saída solicitados e o status de aprovação atual.",
            },
            3: {
                "title": "Aba Todas as Presenças",
                "description": "Acesse a aba Todas as Presenças para ver todos os registros de presença de todos os funcionários — incluindo os que nunca foram sinalizados para correção. Use isso para uma visão de auditoria completa.",
            },
            4: {
                "title": "Lista de Registros",
                "description": "Cada linha da lista mostra o nome do funcionário, os detalhes originais de presença, os valores corrigidos que ele solicitou e se a solicitação está pendente, aprovada ou rejeitada. Clique em uma linha para abrir os detalhes completos e agir.",
            },
            5: {
                "title": "Nova Solicitação de Presença",
                "description": "Clique em Criar para enviar uma nova solicitação de presença em nome de um funcionário — útil quando um administrador precisa adicionar ou corrigir um registro diretamente. Preencha o funcionário, a data, os horários de entrada e saída e o motivo da alteração.",
            },
            6: {
                "title": "Aprovar e Rejeitar",
                "description": "Clique em qualquer linha de solicitação para abrir sua visualização de detalhes, onde você pode aprová-la ou rejeitá-la. Use Ações → Aprovar em Massa ou Rejeitar em Massa para processar várias solicitações selecionadas de uma vez.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "hour-account-tour": {
        "title": "Conta de Horas",
        "description": "Um tour guiado pela página de Conta de Horas — acompanhando, aprovando e exportando as horas extras dos funcionários.",
        "steps": {
            1: {
                "title": "Conta de Horas",
                "description": "A página de Conta de Horas acompanha as horas extras (HE) de cada funcionário. Todo registro de presença que inclui horas extras contribui para esse saldo, que pode depois ser transferido, convertido em pagamento ou usado como licença compensatória, dependendo da política da sua organização.",
            },
            2: {
                "title": "Lista de Registros de Horas Extras",
                "description": "Cada linha mostra o registro de horas extras de um funcionário — a data, o número de horas extras registradas, o status de validação e se as horas extras foram aprovadas ou ainda estão pendentes. Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Adicionar Registro de Horas Extras",
                "description": "Clique em Criar para adicionar manualmente um registro de horas extras para um funcionário. Informe o funcionário, a data e o número de horas extras. Isso é útil quando as horas extras são controladas fora do sistema padrão de ponto.",
            },
            4: {
                "title": "Status de Aprovação",
                "description": "Cada registro de horas extras tem um indicador de status — pendente, aprovado ou validado. Os registros aprovados são confirmados por um administrador; os registros validados já foram processados para fins de folha de pagamento ou licença compensatória.",
            },
            5: {
                "title": "Exportar",
                "description": "Use Ações → Exportar para baixar os dados da conta de horas como uma planilha. Você pode exportar resultados filtrados para compartilhar com as equipes de folha de pagamento ou para relatórios de conformidade.",
            },
            6: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "attendance-activity-tour": {
        "title": "Atividade de Presença",
        "description": "Um tour guiado pela página de Atividade de Presença — visualizando, importando e exportando registros individuais de entrada e saída.",
        "steps": {
            1: {
                "title": "Atividade de Presença",
                "description": "A página de Atividade de Presença fornece um registro detalhado de cada evento de entrada e saída registrado pelo sistema. Diferente da lista principal de presença, que mostra um registro por dia, esta visualização mostra cada entrada de atividade individual — útil para auditar eventos de registro por terminal ou biometria.",
            },
            2: {
                "title": "Registro de Atividade",
                "description": "Cada linha mostra uma atividade de presença individual — o nome do funcionário, a data, o horário de entrada, o horário de saída e a duração total. Clique em qualquer linha para abrir a visualização completa de detalhes daquela atividade.",
            },
            3: {
                "title": "Importar Dados de Atividade",
                "description": "Use Ações → Importar para enviar registros de atividade de presença a partir de uma planilha. Isso é útil quando você recebe dados brutos de ponto de um dispositivo ou sistema externo de controle de tempo.",
            },
            4: {
                "title": "Exportar Dados de Atividade",
                "description": "Use Ações → Exportar para baixar o registro de atividade como uma planilha. Você pode aplicar filtros antes para que a exportação inclua apenas o período ou os funcionários que você precisa.",
            },
            5: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "late-come-early-out-tour": {
        "title": "Atraso e Saída Antecipada",
        "description": "Um tour guiado pela página de Atraso e Saída Antecipada — revisando exceções de presença, entendendo penalidades e exportando relatórios de exceções.",
        "steps": {
            1: {
                "title": "Atraso e Saída Antecipada",
                "description": "Esta página acompanha exceções de presença — funcionários que registraram entrada atrasada ou saíram antes do término do turno. Cada registro é gerado automaticamente quando uma entrada de presença não atende ao horário de entrada ou saída exigido pelo turno atribuído.",
            },
            2: {
                "title": "Registros de Exceção",
                "description": "Cada linha mostra o nome do funcionário, a data da presença, o tipo de exceção (Atraso ou Saída Antecipada), quantos minutos de atraso ou antecipação houve, e se uma penalidade foi aplicada. Clique em qualquer linha para abrir o detalhe completo.",
            },
            3: {
                "title": "Atraso",
                "description": "Um registro de Atraso é criado quando o horário de entrada de um funcionário é posterior ao horário de início definido no turno dele. A duração do atraso é calculada automaticamente e exibida no registro.",
            },
            4: {
                "title": "Saída Antecipada",
                "description": "Um registro de Saída Antecipada é criado quando um funcionário registra saída antes do horário de término programado do turno. A duração da saída antecipada é registrada e pode gerar uma penalidade, se a política da sua organização exigir.",
            },
            5: {
                "title": "Regras de Penalidade",
                "description": "Se sua organização tiver regras de penalidade configuradas, elas são aplicadas automaticamente aos registros de atraso ou saída antecipada. Clique na linha de um registro para ver ou gerenciar a penalidade aplicada a essa exceção.",
            },
            6: {
                "title": "Exportar",
                "description": "Use Ações → Exportar para baixar os registros de atraso e saída antecipada como uma planilha. Aplique filtros antes de exportar para obter o período ou departamento específico que você precisa.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "my-attendances-tour": {
        "title": "Minhas Presenças",
        "description": "Um tour guiado pela página Minhas Presenças — revisando seus próprios registros de presença, entendendo o status de validação e abrindo solicitações de correção.",
        "steps": {
            1: {
                "title": "Minhas Presenças",
                "description": "Esta página mostra seus próprios registros de presença — todos os dias em que você registrou entrada e saída. Você pode revisar seu histórico de presença, verificar o status de validação, abrir solicitações de correção e acompanhar suas horas extras, tudo em um só lugar.",
            },
            2: {
                "title": "Seus Registros de Presença",
                "description": "Cada linha mostra a presença de um dia — seu horário de entrada, horário de saída, turno, tipo de trabalho, carga horária mínima exigida, horas trabalhadas e quaisquer horas extras obtidas. Clique em uma linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Data, Entrada, Saída, Turno, Tipo de Trabalho, Carga Horária Mínima, No Trabalho, Horas Pendentes e Horas Extras.",
            },
            4: {
                "title": "Status de Validação",
                "description": "Cada linha tem uma borda esquerda colorida mostrando seu status — validada (confirmada pelo administrador), não validada (aguardando revisão), correção solicitada (aguardando ação do administrador) ou correção aprovada.",
            },
            5: {
                "title": "Solicitar uma Correção",
                "description": "Se você notar um erro — como uma saída não registrada ou um horário de entrada incorreto — clique na linha para abrir o registro e enviar uma solicitação de correção. Seu administrador vai revisar e aprovar ou rejeitar.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir seus registros por intervalo de datas, turno, tipo de trabalho ou status de validação — útil ao revisar um período de pagamento específico ou localizar uma entrada faltante.",
            },
        },
    },
    "my-leave-request-tour": {
        "title": "Minhas Solicitações de Licença",
        "description": "Um tour guiado pela página Minhas Solicitações de Licença — enviando, acompanhando e gerenciando suas solicitações pessoais de licença.",
        "steps": {
            1: {
                "title": "Minhas Solicitações de Licença",
                "description": "Esta página mostra todas as solicitações de licença que você enviou. Você pode acompanhar o status de cada solicitação, ver os detalhes das licenças aprovadas ou rejeitadas, e enviar novas solicitações de licença diretamente daqui.",
            },
            2: {
                "title": "Suas Solicitações de Licença",
                "description": "Cada linha mostra uma solicitação de licença — o tipo de licença, as datas de início e término, o número de dias solicitados, o status atual e um botão de cancelar. Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Solicitar uma Licença",
                "description": "Clique em Criar para enviar uma nova solicitação de licença. Selecione o tipo de licença, defina as datas de início e término, adicione um motivo se necessário, e envie. Seu administrador será notificado para revisar e aprovar ou rejeitar.",
            },
            4: {
                "title": "Status da Solicitação",
                "description": "Cada linha tem uma borda esquerda colorida mostrando o status — Solicitado (aguardando revisão do administrador), Aprovado (aceito, dias deduzidos do saldo), Rejeitado (recusado) ou Cancelado (retirado por você).",
            },
            5: {
                "title": "Cancelar uma Solicitação",
                "description": "Cada linha tem um botão Cancelar na última coluna. Clique nele para retirar uma solicitação de licença aprovada antes da data de término. Cancelar devolve os dias deduzidos ao seu saldo de licença.",
            },
            6: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Tipo de Licença, Data de Início, Data de Término, Dias Solicitados, Status e Comentário.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar suas solicitações de licença por tipo de licença ou palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir suas solicitações por tipo de licença, status, intervalo de datas ou número de dias solicitados. Use Agrupar Por para reorganizar a lista por tipo de licença ou status para uma visão rápida.",
            },
        },
    },
    "leave-requests-tour": {
        "title": "Solicitações de Licença",
        "description": "Um tour guiado pela página de Solicitações de Licença — revisando, aprovando, rejeitando e gerenciando as solicitações de licença dos funcionários.",
        "steps": {
            1: {
                "title": "Solicitações de Licença",
                "description": "Esta página é o local central para gerenciar todas as solicitações de licença dos funcionários da sua organização. Você pode revisar solicitações pendentes, aprová-las ou rejeitá-las, verificar conflitos de licença e acompanhar o histórico completo de licenças de cada funcionário.",
            },
            2: {
                "title": "Lista de Solicitações",
                "description": "Cada linha mostra uma solicitação de licença — o nome do funcionário, tipo de licença, datas de início e término, número de dias solicitados, indicador de conflito de licença e o status de aprovação atual. Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Criar uma Solicitação de Licença",
                "description": "Clique em Criar para abrir uma solicitação de licença em nome de um funcionário — útil quando um administrador precisa registrar uma licença diretamente. Selecione o funcionário, o tipo de licença e as datas, depois envie.",
            },
            4: {
                "title": "Ações em Massa",
                "description": "Clique em Ações para aprovar ou rejeitar em massa as solicitações selecionadas de uma vez, ou para exportar a lista como uma planilha. Selecione as linhas usando as caixas de seleção primeiro.",
            },
            5: {
                "title": "Aprovar",
                "description": "Cada linha de solicitação pendente tem um botão Aprovar. Clique nele para aceitar a licença — o saldo de licença do funcionário é deduzido imediatamente e ele é notificado.",
            },
            6: {
                "title": "Rejeitar",
                "description": "Clique no botão Rejeitar em uma linha de solicitação para recusar a licença. Você será solicitado a informar um motivo, que será enviado de volta ao funcionário.",
            },
            7: {
                "title": "Conflitos de Licença",
                "description": "O ícone de grupos em cada linha mostra quantos colegas de equipe têm licença sobreposta nas mesmas datas. Clique nele para abrir os detalhes do conflito e ver quem mais está ausente antes de decidir se aprova.",
            },
            8: {
                "title": "Alternar Colunas",
                "description": "Clique no botão de configurações de colunas no canto superior direito da tabela para mostrar ou ocultar colunas — Funcionário, Tipo de Licença, Data de Início, Data de Término, Dias Solicitados, Conflito de Licença, Status e mais.",
            },
            9: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar solicitações por nome do funcionário. A lista é atualizada conforme você digita — útil ao gerenciar licenças em uma equipe grande.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por tipo de licença, status, intervalo de datas, departamento ou administrador responsável. Use Agrupar Por para organizar as solicitações por funcionário, tipo de licença ou data.",
            },
        },
    },
    "leave-type-tour": {
        "title": "Tipos de Licença",
        "description": "Um tour guiado pela página de Tipos de Licença — criando, configurando e gerenciando as categorias de licença da sua organização.",
        "steps": {
            1: {
                "title": "Tipos de Licença",
                "description": "Tipos de Licença definem as categorias de licença disponíveis na sua organização — como Licença Anual, Licença Médica, Licença Maternidade e Licença Compensatória. Cada tipo de licença tem suas próprias regras de acúmulo, limites de transferência, fluxo de aprovação e elegibilidade.",
            },
            2: {
                "title": "Lista de Tipos de Licença",
                "description": "Cada linha mostra um tipo de licença configurado — seu nome, o número de dias permitidos por ano, se exige aprovação, se os dias não utilizados podem ser transferidos e se acumula com o tempo.",
            },
            3: {
                "title": "Criar um Tipo de Licença",
                "description": "Clique em Criar para definir um novo tipo de licença. Defina o nome, o total de dias permitidos, a exigência de aprovação, o limite de transferência, as configurações de acúmulo e quaisquer restrições de elegibilidade, como gênero ou período de experiência.",
            },
            4: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use os botões de alternância de visualização no canto superior direito para trocar entre a visualização em Lista (tabular) e a visualização em Cartão (blocos visuais). A visualização em Cartão dá uma visão rápida de cada tipo de licença com suas configurações principais em um só olhar.",
            },
            5: {
                "title": "Transferência e Acúmulo",
                "description": "Cada tipo de licença pode ser configurado para transferir os dias não utilizados para o próximo período de licença e para acumular dias com o tempo, com base no tempo de empresa ou nos dias trabalhados do funcionário. Essas configurações controlam como os saldos crescem e são transferidos.",
            },
            6: {
                "title": "Editar e Excluir",
                "description": "Clique no ícone de edição em qualquer tipo de licença para atualizar sua configuração. Use o ícone de exclusão para remover um tipo de licença que não está mais em uso — observe que excluir um tipo de licença também remove quaisquer saldos de licença atribuídos vinculados a ele.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "assigned-leaves-tour": {
        "title": "Todas as Licenças Atribuídas",
        "description": "Um tour guiado pela página Todas as Licenças Atribuídas — visualizando, atribuindo e gerenciando os saldos de licença dos funcionários em todos os tipos de licença.",
        "steps": {
            1: {
                "title": "Todas as Licenças Atribuídas",
                "description": "Esta página mostra os saldos de licença atribuídos a todos os funcionários em todos os tipos de licença. Cada registro representa a alocação de um funcionário para um tipo de licença específico — incluindo o total de dias concedidos, dias usados, dias restantes e qualquer saldo transferido.",
            },
            2: {
                "title": "Saldos de Licença Atribuídos",
                "description": "Cada linha mostra uma atribuição — o nome do funcionário, tipo de licença, total de dias alocados, dias já usados, saldo restante e dias transferidos do período anterior. Clique em qualquer linha para abrir os detalhes completos e fazer ajustes.",
            },
            3: {
                "title": "Atribuir Licença",
                "description": "Clique em Atribuir para alocar um tipo de licença a um ou mais funcionários. Escolha o tipo de licença, defina o número de dias e o período de validade. Você pode atribuir a funcionários individuais ou a um departamento inteiro de uma vez.",
            },
            4: {
                "title": "Ajustar Saldos",
                "description": "Abra qualquer registro para ajustar manualmente o saldo de licença de um funcionário — por exemplo, para adicionar dias extras, corrigir um erro ou considerar uma exceção de política. Todos os ajustes são registrados para fins de auditoria.",
            },
            5: {
                "title": "Transferência",
                "description": "A coluna Dias Transferidos mostra quantos dias não utilizados foram transferidos do período de licença anterior. Isso é controlado pelas configurações de transferência de cada tipo de licença.",
            },
            6: {
                "title": "Importar e Exportar",
                "description": "Use Ações → Importar para atribuir saldos de licença em massa a partir de uma planilha. Use Ações → Exportar para baixar os saldos atuais para relatórios ou reconciliação com a folha de pagamento.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "leave-allocation-requests-tour": {
        "title": "Solicitações de Alocação de Licença",
        "description": "Um tour guiado pela página de Solicitações de Alocação de Licença — enviando, revisando e aprovando solicitações de dias adicionais de licença.",
        "steps": {
            1: {
                "title": "Solicitações de Alocação de Licença",
                "description": "Esta página gerencia solicitações de dias adicionais de licença. Os funcionários podem solicitar alocação extra além do direito padrão — por exemplo, solicitando dias adicionais de licença anual. Os administradores revisam e aprovam ou rejeitam essas solicitações aqui.",
            },
            2: {
                "title": "Aba Minhas Solicitações",
                "description": "A aba Minha Solicitação de Alocação de Licença mostra todas as solicitações de alocação que você mesmo enviou — incluindo o status de aprovação atual e o número de dias solicitados.",
            },
            3: {
                "title": "Aba Todas as Solicitações",
                "description": "A aba Solicitações de Alocação de Licença mostra todas as solicitações enviadas pelos funcionários da sua equipe. Use esta aba para revisar solicitações pendentes e tomar ações de aprovação.",
            },
            4: {
                "title": "Lista de Solicitações",
                "description": "Cada linha mostra uma solicitação de alocação — o nome do funcionário, o tipo de licença para o qual está solicitando dias extras, o número de dias solicitados, o motivo informado e o status atual (pendente, aprovado ou rejeitado).",
            },
            5: {
                "title": "Nova Solicitação de Alocação",
                "description": "Clique em Criar para enviar uma nova solicitação de alocação em nome de um funcionário. Selecione o funcionário, o tipo de licença, o número de dias adicionais necessários e o motivo da solicitação.",
            },
            6: {
                "title": "Aprovar e Rejeitar",
                "description": "Clique em qualquer linha de solicitação para abrir sua visualização de detalhes, onde você pode aprová-la ou rejeitá-la. Aprovar uma solicitação adiciona automaticamente os dias alocados ao saldo de licença do funcionário para aquele tipo de licença.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "compensatory-leave-requests-tour": {
        "title": "Solicitações de Licença Compensatória",
        "description": "Um tour guiado pela página de Solicitações de Licença Compensatória — enviando, revisando e aprovando licença compensatória para funcionários que trabalham em feriados ou dias de descanso.",
        "steps": {
            1: {
                "title": "Solicitações de Licença Compensatória",
                "description": "Esta página gerencia a licença compensatória — dias adicionais de licença concedidos a funcionários que trabalham em feriados ou fora do horário programado. Os funcionários podem enviar solicitações de licença compensatória, e os administradores revisam e aprovam ou rejeitam aqui.",
            },
            2: {
                "title": "Aba Minhas Solicitações",
                "description": "A aba Minhas Solicitações de Licença Compensatória mostra todas as solicitações de licença compensatória que você mesmo enviou — incluindo as datas trabalhadas, o número de dias compensatórios solicitados e o status de aprovação atual.",
            },
            3: {
                "title": "Aba Todas as Solicitações",
                "description": "A aba Solicitações de Licença Compensatória mostra todas as solicitações enviadas pelos funcionários da sua equipe. Use esta aba para revisar solicitações pendentes e tomar ações de aprovação ou rejeição.",
            },
            4: {
                "title": "Lista de Solicitações",
                "description": "Cada linha mostra uma solicitação de licença compensatória — o nome do funcionário, a data em que ele trabalhou extra, o número de dias compensatórios solicitados e o status atual. Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            5: {
                "title": "Nova Solicitação Compensatória",
                "description": "Clique em Criar para enviar uma nova solicitação de licença compensatória. Selecione o funcionário, a data em que ele trabalhou (em um feriado ou dia de descanso) e o número de dias compensatórios solicitados.",
            },
            6: {
                "title": "Aprovar e Rejeitar",
                "description": "Clique em qualquer linha de solicitação para abrir sua visualização de detalhes, onde você pode aprová-la ou rejeitá-la. Aprovar uma solicitação de licença compensatória adiciona automaticamente os dias ao saldo de licença do funcionário.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "contracts-tour": {
        "title": "Contratos",
        "description": "Um tour guiado pela página de Contratos — criando, gerenciando e revisando os contratos de trabalho dos funcionários e suas estruturas salariais.",
        "steps": {
            1: {
                "title": "Contratos",
                "description": "A página de Contratos armazena e gerencia os contratos de trabalho dos seus funcionários. Cada contrato define a estrutura salarial do funcionário, o tipo de contrato, o período de validade e os detalhes salariais usados nos cálculos da folha de pagamento.",
            },
            2: {
                "title": "Lista de Contratos",
                "description": "Cada linha mostra um contrato — o nome do funcionário, o tipo de contrato (permanente, temporário, freelancer etc.), datas de início e término, o valor do salário e o status atual do contrato. Clique em qualquer linha para abrir os detalhes completos do contrato.",
            },
            3: {
                "title": "Criar um Contrato",
                "description": "Clique em Criar para adicionar um novo contrato para um funcionário. Defina o tipo de contrato, as datas de início e término, informe o salário básico e configure quaisquer auxílios ou deduções que se aplicam a este contrato.",
            },
            4: {
                "title": "Status do Contrato",
                "description": "Cada linha tem uma lista de status embutida — Ativo (atualmente em vigor), Rascunho, Expirado ou Rescindido. Altere o status diretamente na lista sem abrir os detalhes completos do contrato.",
            },
            5: {
                "title": "Salário e Estrutura de Pagamento",
                "description": "Os detalhes salariais de cada contrato alimentam diretamente a folha de pagamento. O salário básico, junto com quaisquer auxílios e deduções vinculados, determina o salário líquido do funcionário em cada período de pagamento.",
            },
            6: {
                "title": "Exportar",
                "description": "Use Ações → Exportar para baixar a lista de contratos como uma planilha. Útil para relatórios, auditoria dos termos de trabalho ou compartilhamento de dados com as equipes jurídica ou financeira.",
            },
            7: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "allowances-tour": {
        "title": "Auxílios",
        "description": "Um tour guiado pela página de Auxílios — criando e gerenciando auxílios salariais incluídos nos cálculos de folha de pagamento dos funcionários.",
        "steps": {
            1: {
                "title": "Auxílios",
                "description": "Auxílios são componentes salariais adicionais somados ao salário básico do funcionário — como auxílio-moradia, auxílio-transporte, auxílio-alimentação ou bônus por desempenho. Cada auxílio definido aqui pode ser vinculado aos contratos dos funcionários e incluído automaticamente nos cálculos da folha de pagamento.",
            },
            2: {
                "title": "Lista de Auxílios",
                "description": "Cada linha mostra um auxílio configurado — seu nome, o valor ou percentual, se é tributável, se é um valor fixo ou baseado em uma condição, e se está ativo atualmente.",
            },
            3: {
                "title": "Criar um Auxílio",
                "description": "Clique em Criar para definir um novo auxílio. Defina o nome, escolha se é um valor fixo ou um percentual do salário básico, marque-o como tributável ou não tributável, e configure quaisquer condições que determinem quando ele se aplica.",
            },
            4: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use os botões de alternância de visualização para trocar entre a visualização em Lista e a visualização em Cartão. A visualização em Cartão oferece uma visão visual compacta de cada auxílio com seus detalhes principais em um só olhar.",
            },
            5: {
                "title": "Valor Fixo ou Percentual",
                "description": "Um auxílio pode ser um valor fixo (por exemplo, R$ 200 por mês) ou um percentual do salário básico do funcionário (por exemplo, 10%). Auxílios baseados em percentual se ajustam automaticamente quando o salário básico muda.",
            },
            6: {
                "title": "Auxílios Condicionais",
                "description": "Os auxílios podem ser tornados condicionais — por exemplo, aplicando-se apenas a funcionários de um departamento, cargo ou turno específico, ou apenas quando um determinado limite de presença é atingido. As condições são configuradas dentro do detalhe do auxílio.",
            },
            7: {
                "title": "Editar e Excluir",
                "description": "Clique em qualquer linha de auxílio para editar sua configuração. Você pode atualizar o valor, a tributabilidade, as condições ou o status ativo. Excluir um auxílio o remove de todas as futuras execuções de folha de pagamento, mas não afeta os holerites históricos.",
            },
        },
    },
    "deductions-tour": {
        "title": "Deduções",
        "description": "Um tour guiado pela página de Deduções — criando e gerenciando deduções salariais aplicadas durante os cálculos de folha de pagamento dos funcionários.",
        "steps": {
            1: {
                "title": "Deduções",
                "description": "Deduções são valores subtraídos do salário bruto de um funcionário antes de calcular o salário final — como imposto de renda, contribuições previdenciárias, pagamentos de empréstimos ou deduções por ausência. Cada dedução definida aqui pode ser vinculada aos contratos e aplicada automaticamente durante as execuções da folha de pagamento.",
            },
            2: {
                "title": "Lista de Deduções",
                "description": "Cada linha mostra uma dedução configurada — seu nome, o valor ou percentual, se é uma dedução antes ou depois dos impostos, se é baseada em uma condição, e se está ativa atualmente.",
            },
            3: {
                "title": "Criar uma Dedução",
                "description": "Clique em Criar para definir uma nova dedução. Defina o nome, escolha se é um valor fixo ou um percentual do salário básico, configure o tratamento antes ou depois dos impostos, e adicione quaisquer condições que determinem quando ela se aplica.",
            },
            4: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use os botões de alternância de visualização para trocar entre a visualização em Lista e a visualização em Cartão. A visualização em Cartão oferece uma visão visual compacta de cada dedução com suas configurações principais em um só olhar.",
            },
            5: {
                "title": "Valor Fixo ou Percentual",
                "description": "Uma dedução pode ser um valor fixo (por exemplo, R$ 50 por mês) ou um percentual do salário básico do funcionário (por exemplo, 5%). Deduções baseadas em percentual são recalculadas automaticamente quando o salário básico muda.",
            },
            6: {
                "title": "Deduções Condicionais",
                "description": "As deduções podem ser tornadas condicionais — por exemplo, aplicando-se apenas a funcionários acima de um determinado limite salarial, em um departamento específico, ou com base em critérios de presença. As condições são configuradas dentro do detalhe da dedução.",
            },
            7: {
                "title": "Editar e Excluir",
                "description": "Clique em qualquer linha de dedução para editar sua configuração — atualize o valor, as condições ou o status ativo. Excluir uma dedução a remove das futuras execuções de folha de pagamento, mas não afeta os holerites históricos.",
            },
        },
    },
    "payslip-tour": {
        "title": "Holerites",
        "description": "Um tour guiado pela página de Holerites — gerando, revisando, confirmando e distribuindo os holerites dos funcionários.",
        "steps": {
            1: {
                "title": "Holerites",
                "description": "A página de Holerites é onde os holerites dos funcionários são criados, revisados e processados. Cada holerite calcula o salário líquido de um funcionário para um período específico com base no contrato, auxílios, deduções e dados de presença.",
            },
            2: {
                "title": "Lista de Holerites",
                "description": "Cada linha mostra um holerite — o nome do funcionário, o período de pagamento, o salário básico, o salário líquido e o status atual. Clique em qualquer linha para abrir o detalhe individual do holerite, onde você pode revisar o detalhamento completo do pagamento.",
            },
            3: {
                "title": "Status do Holerite",
                "description": "Cada holerite tem um status: Rascunho (criado, mas ainda não revisado), Revisão em Andamento (enviado para revisão do funcionário), Confirmado (aprovado e pronto para pagamento) e Pago (o salário foi desembolsado). Use a lista de status embutida em cada linha para atualizar o status diretamente na lista.",
            },
            4: {
                "title": "Criar um Holerite",
                "description": "Clique em Criar para gerar um holerite para um funcionário individual. Selecione o funcionário, defina as datas de início e término do período de pagamento, e o sistema calculará automaticamente o pagamento com base no contrato ativo, auxílios e deduções.",
            },
            5: {
                "title": "Gerar Holerites em Massa",
                "description": "Use Ações → Gerar para criar holerites para todos os funcionários de uma vez para um período de pagamento selecionado. O sistema processa o contrato de cada funcionário e gera holerites individuais em massa — economizando tempo no final de cada ciclo de folha de pagamento.",
            },
            6: {
                "title": "Enviar para Revisão e Confirmar",
                "description": "Depois que os holerites são gerados, envie-os aos funcionários para revisão. Após o período de revisão, confirme os holerites para bloquear os valores. Os holerites confirmados podem então ser marcados como Pagos depois que a transferência do salário for concluída.",
            },
            7: {
                "title": "Enviar por E-mail e Exportar",
                "description": "Use Ações → Enviar por E-mail para enviar os holerites diretamente aos funcionários. Use Ações → Exportar ou Relatório de Holerite para baixar os dados dos holerites como uma planilha para fins financeiros ou de auditoria.",
            },
            8: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            9: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "loan-advance-salary-tour": {
        "title": "Empréstimo / Adiantamento Salarial",
        "description": "Um tour guiado pela página de Empréstimo / Adiantamento Salarial — concedendo empréstimos, adiantamentos salariais e multas, e acompanhando deduções automáticas na folha de pagamento.",
        "steps": {
            1: {
                "title": "Empréstimo / Adiantamento Salarial",
                "description": "Esta página gerencia a assistência financeira aos funcionários — empréstimos pagos em parcelas, adiantamentos salariais tirados sobre ganhos futuros, e multas aplicadas por violações de política. Os três são acompanhados aqui e considerados automaticamente nas deduções da folha de pagamento.",
            },
            2: {
                "title": "Aba Empréstimo",
                "description": "A aba Empréstimo mostra todos os empréstimos de funcionários ativos e concluídos. Cada registro mostra o nome do funcionário, o valor do empréstimo, o número de parcelas, o valor já pago e o saldo pendente.",
            },
            3: {
                "title": "Aba Adiantamento Salarial",
                "description": "A aba Adiantamento Salarial mostra as solicitações de adiantamento salarial — quando um funcionário retira antecipadamente parte do salário futuro. O adiantamento é deduzido automaticamente do próximo holerite ou distribuído em vários períodos de pagamento.",
            },
            4: {
                "title": "Aba Multa",
                "description": "A aba Multa registra deduções de penalidade aplicadas aos funcionários — por exemplo, por violações de presença, quebras de política ou ações disciplinares. As multas são deduzidas do holerite do funcionário no período configurado.",
            },
            5: {
                "title": "Lista de Registros",
                "description": "Cada linha na aba ativa mostra o funcionário, o valor, o cronograma de parcelas e o status de pagamento atual. Clique em qualquer linha para abrir a visualização completa de detalhes, incluindo o histórico completo de pagamentos.",
            },
            6: {
                "title": "Criar um Empréstimo ou Adiantamento",
                "description": "Clique em Criar para conceder um novo empréstimo ou adiantamento salarial. Selecione o funcionário, defina o valor total, configure o número de parcelas e a data de início. O sistema vai agendar automaticamente as deduções nos períodos de pagamento especificados.",
            },
            7: {
                "title": "Dedução Automática na Folha de Pagamento",
                "description": "Depois que um empréstimo ou adiantamento é criado, os valores das parcelas são deduzidos automaticamente do holerite do funcionário em cada período até o saldo ser zerado. Nenhum ajuste manual é necessário — a folha de pagamento cuida disso automaticamente.",
            },
            8: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            9: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "reimbursements-tour": {
        "title": "Reembolsos",
        "description": "Um tour guiado pela página de Reembolsos — enviando, aprovando e processando reembolsos de despesas, conversão de licença em dinheiro e conversão de bônus em dinheiro.",
        "steps": {
            1: {
                "title": "Reembolsos",
                "description": "Esta página gerencia os reembolsos e conversões em dinheiro dos funcionários — despesas que os funcionários pagaram do próprio bolso e que a empresa reembolsa, além de conversões de licença e bônus em dinheiro. Todos os valores aprovados são incluídos automaticamente no próximo holerite.",
            },
            2: {
                "title": "Aba Reembolsos",
                "description": "A aba Reembolsos mostra todas as solicitações de reembolso de despesas — como viagens, despesas médicas ou equipamentos. Cada linha mostra o funcionário, o valor solicitado, o tipo de reembolso e o status de aprovação atual.",
            },
            3: {
                "title": "Aba Conversão de Licença em Dinheiro",
                "description": "A aba Conversão de Licença em Dinheiro mostra as solicitações para converter dias de licença não utilizados em dinheiro. Os funcionários podem converter saldos de licença elegíveis com base na política de conversão da sua organização.",
            },
            4: {
                "title": "Aba Conversão de Bônus em Dinheiro",
                "description": "A aba Conversão de Bônus em Dinheiro mostra as solicitações para converter pontos de bônus acumulados ou direitos em dinheiro. Depois de aprovada, o valor convertido é adicionado ao holerite do funcionário.",
            },
            5: {
                "title": "Lista de Solicitações",
                "description": "Cada linha na aba ativa mostra o funcionário, o valor solicitado, a data da solicitação e o status de aprovação. Clique em qualquer linha para abrir a visualização completa de detalhes, incluindo recibos anexados ou documentos de apoio.",
            },
            6: {
                "title": "Criar uma Solicitação",
                "description": "Clique em Criar para enviar uma nova solicitação de reembolso. Selecione o funcionário, escolha o tipo de reembolso, informe o valor, anexe quaisquer recibos de apoio e envie para aprovação do administrador.",
            },
            7: {
                "title": "Aprovação e Integração com o Holerite",
                "description": "Os reembolsos aprovados são adicionados automaticamente ao próximo holerite do funcionário como um adicional não tributável. Nenhum lançamento manual na folha de pagamento é necessário — depois de aprovado, o valor entra na próxima execução da folha de pagamento.",
            },
            8: {
                "title": "Buscar",
                "description": "Use a barra de busca para encontrar rapidamente registros pelo nome do funcionário ou por palavra-chave. A lista é atualizada conforme você digita.",
            },
            9: {
                "title": "Filtrar",
                "description": "Clique no botão Filtrar para abrir o painel de filtros. Use os campos disponíveis para restringir os resultados por período, departamento, status ou outros critérios e clique em Aplicar para atualizar a lista.",
            },
        },
    },
    "objectives-tour": {
        "title": "Objetivos",
        "description": "Um tour guiado pela página de Objetivos — criando objetivos, adicionando Resultados-Chave, acompanhando o progresso e gerenciando OKRs em toda a sua organização.",
        "steps": {
            1: {
                "title": "Objetivos",
                "description": "A página de Objetivos é onde os OKRs (Objetivos e Resultados-Chave) da sua organização são gerenciados. Cada objetivo define uma meta de alto nível, e os Resultados-Chave definem resultados mensuráveis que acompanham o progresso em direção a ela.",
            },
            2: {
                "title": "Aba Objetivos Atribuídos",
                "description": "A aba Objetivos Atribuídos mostra todos os objetivos que foram atribuídos a você como funcionário ou responsável. Use esta aba para acompanhar suas próprias metas e atualizar o progresso dos seus Resultados-Chave.",
            },
            3: {
                "title": "Aba Todos os Objetivos",
                "description": "A aba Todos os Objetivos lista todos os objetivos da organização — incluindo os que você gerencia. Administradores usam esta aba para criar novos objetivos, revisar o progresso da equipe e gerenciar os responsáveis.",
            },
            4: {
                "title": "Lista de Objetivos",
                "description": "Cada linha mostra um objetivo — seu título, administradores designados, o número de Resultados-Chave, a lista de responsáveis, a duração e uma breve descrição. Clique em qualquer linha para expandi-la e ver os Resultados-Chave abaixo.",
            },
            5: {
                "title": "Barra de Progresso",
                "description": "A barra de progresso em cada linha de objetivo mostra o percentual de conclusão geral, calculado automaticamente a partir do progresso de todos os Resultados-Chave vinculados. Conforme os funcionários atualizam seus valores de Resultado-Chave, a barra é atualizada em tempo real.",
            },
            6: {
                "title": "Criar Objetivo",
                "description": "Clique em Criar para definir um novo objetivo. Defina o título, adicione uma descrição, atribua administradores e funcionários, defina as datas de início e término, e adicione os Resultados-Chave que vão medir o sucesso.",
            },
            7: {
                "title": "Adicionar Resultados-Chave",
                "description": "Clique no botão + em qualquer linha de objetivo para adicionar um Resultado-Chave a ele. Cada Resultado-Chave tem um título, um valor-alvo, uma unidade de medida (número, percentual, moeda) e datas de início e término. O progresso é atualizado ao informar o valor atual.",
            },
            8: {
                "title": "Ações da Linha",
                "description": "Cada linha de objetivo tem botões de ação — Visualizar (ícone de olho) para abrir o detalhe completo, Atividade (ícone de jornal) para ver o registro de alterações, e o menu de três pontos para Editar, Arquivar ou Excluir o objetivo.",
            },
            9: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar objetivos rapidamente por título. A lista é atualizada conforme você digita.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os objetivos por responsável, resultado-chave, intervalo de datas, status ou percentual de progresso. Uma segunda seção permite filtrar por datas de Resultado-Chave e status de vencimento.",
            },
        },
    },
    "objective-templates-tour": {
        "title": "Modelos de Objetivo",
        "description": "Um tour guiado pela página de Modelos de Objetivo — criando estruturas reutilizáveis de objetivo com Resultados-Chave predefinidos que podem ser aplicadas a qualquer funcionário.",
        "steps": {
            1: {
                "title": "Modelos de Objetivo",
                "description": "Modelos de Objetivo são estruturas reutilizáveis de objetivo. Em vez de criar a mesma estrutura de objetivo do zero a cada trimestre, você a define uma vez como um modelo — com Resultados-Chave, durações e descrições predefinidos — e depois a aplica para criar objetivos reais para qualquer funcionário.",
            },
            2: {
                "title": "Lista de Modelos",
                "description": "Cada linha mostra um modelo — seu título, os administradores atribuídos a ele, os Resultados-Chave que contém, os responsáveis e a duração. Clique em qualquer linha para abrir os detalhes completos do modelo.",
            },
            3: {
                "title": "Criar Modelo",
                "description": "Clique em Criar para definir um novo modelo de objetivo. Defina o título, adicione uma descrição, anexe Resultados-Chave padrão com valores-alvo e unidades, e salve. O modelo pode então ser reutilizado para criar rapidamente objetivos para qualquer membro da equipe.",
            },
            4: {
                "title": "Aplicando um Modelo",
                "description": "Para usar um modelo, abra-o e atribua-o a um funcionário. O sistema cria um objetivo real com todos os Resultados-Chave predefinidos já vinculados — economizando tempo ao integrar novos membros da equipe ou executar ciclos de metas recorrentes.",
            },
            5: {
                "title": "Editar e Excluir",
                "description": "Clique no menu de três pontos em qualquer linha de modelo para Editar ou Excluí-lo. Editar um modelo não afeta os objetivos que já foram criados a partir dele — as alterações se aplicam apenas ao uso futuro do modelo.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar modelos rapidamente por título. A lista é atualizada conforme você digita.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os modelos por responsável, resultado-chave, intervalo de datas, status ou percentual de progresso.",
            },
        },
    },
    "feedbacks-tour": {
        "title": "Feedbacks",
        "description": "Um tour guiado pela página de Feedbacks — criando ciclos de avaliação 360 graus, acompanhando o status do feedback e gerenciando feedback próprio, solicitado e anônimo.",
        "steps": {
            1: {
                "title": "Feedbacks",
                "description": "A página de Feedbacks é o centro das avaliações de desempenho 360 graus. Os funcionários podem ver o próprio feedback, os administradores podem revisar o feedback dado à sua equipe, e o feedback anônimo permite que colegas compartilhem opiniões sinceras sem atribuição.",
            },
            2: {
                "title": "Aba Meu Feedback",
                "description": "A aba Meu Feedback mostra todos os ciclos de feedback atribuídos a você como o funcionário sendo avaliado. Cada linha mostra o título da avaliação, o status e a data de vencimento. Clique em uma linha para abrir o detalhe completo do feedback e ver as perguntas e respostas.",
            },
            3: {
                "title": "Aba Feedback Solicitado",
                "description": "A aba Feedback Solicitado mostra as solicitações de feedback em que você foi convidado a dar sua opinião — como administrador, colega, subordinado ou outro avaliador. Clique em qualquer linha para abrir o formulário de feedback e enviar sua resposta.",
            },
            4: {
                "title": "Aba Feedbacks para Revisar",
                "description": "A aba Feedbacks para Revisar está disponível para administradores. Ela mostra todos os ciclos de feedback dos seus subordinados diretos para que você possa monitorar o progresso, verificar a conclusão e agir sobre avaliações atrasadas ou em risco.",
            },
            5: {
                "title": "Aba Feedback Anônimo",
                "description": "A aba Feedback Anônimo mostra o feedback enviado sem revelar a identidade do avaliador. Use o botão Adicionar Anônimo para criar uma entrada de feedback anônimo para qualquer funcionário.",
            },
            6: {
                "title": "Lista de Feedback",
                "description": "Cada linha mostra o funcionário avaliado, o título do ciclo de avaliação, o status atual (No Prazo, Atrasado, Em Risco, Encerrado), a data de início e a data de vencimento. Clique em qualquer linha para abrir o detalhe completo do feedback.",
            },
            7: {
                "title": "Status do Feedback",
                "description": "Cada linha de feedback tem uma borda esquerda colorida e um indicador de status — verde para No Prazo, laranja para Atrasado, vermelho para Em Risco, azul para Encerrado e cinza para Não Iniciado. Clique em qualquer indicador de status no cabeçalho da lista para filtrar por esse status instantaneamente.",
            },
            8: {
                "title": "Criar Feedback",
                "description": "Clique em Criar para configurar um novo ciclo de feedback. Selecione o funcionário, escolha o período de avaliação, atribua administradores, colegas e subordinados como avaliadores, e escolha o modelo de pergunta. Depois de criado, o sistema notifica todos os avaliadores.",
            },
            9: {
                "title": "Ações",
                "description": "Use o menu Ações para Arquivar ou Desarquivar os ciclos de feedback selecionados, criar Feedback em Massa para vários funcionários de uma vez, ou Excluir as entradas selecionadas.",
            },
            10: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente ciclos de feedback por nome do funcionário ou título da avaliação. A lista é atualizada conforme você digita.",
            },
            11: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os ciclos de feedback por funcionário, status, intervalo de datas, avaliador ou outros critérios.",
            },
        },
    },
    "meetings-tour": {
        "title": "Reuniões",
        "description": "Um tour guiado pela página de Reuniões — agendando reuniões, registrando a Ata de Reunião e acompanhando as conversas entre administrador e funcionário.",
        "steps": {
            1: {
                "title": "Reuniões",
                "description": "A página de Reuniões é onde as reuniões individuais e em grupo entre administradores e funcionários são acompanhadas. Cada registro de reunião armazena a pauta, os participantes, a data e a Ata de Reunião — criando um registro escrito do que foi discutido e acordado.",
            },
            2: {
                "title": "Lista de Reuniões",
                "description": "Cada linha mostra uma reunião — o título, os funcionários convidados, os administradores envolvidos, a data da reunião e um indicador de Ata de Reunião. Clique em qualquer linha para abrir o detalhe completo da reunião em uma janela.",
            },
            3: {
                "title": "Criar Reunião",
                "description": "Clique em Criar para agendar uma nova reunião. Defina o título, selecione o administrador e os funcionários, escolha a data, adicione uma pauta e, opcionalmente, anexe um modelo de pergunta para uma discussão estruturada. Depois da reunião, você pode preencher a Ata diretamente na visualização de detalhes.",
            },
            4: {
                "title": "Ata de Reunião",
                "description": "A coluna de Ata mostra se as atas foram registradas para cada reunião. Depois de uma reunião, abra a visualização de detalhes e preencha o que foi discutido, quaisquer decisões tomadas e itens de ação atribuídos. As entradas de ata se tornam um registro pesquisável das conversas da sua equipe.",
            },
            5: {
                "title": "Detalhe da Reunião",
                "description": "Clique em qualquer linha de reunião para abrir o detalhe completo — participantes, pauta, data, notas da ata e quaisquer respostas de perguntas vinculadas. Os administradores podem editar ou atualizar o registro diretamente nesta visualização.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente reuniões por título ou nome do funcionário. A lista é atualizada conforme você digita.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista de reuniões por funcionário, administrador, intervalo de datas ou status ativo.",
            },
        },
    },
    "key-results-tour": {
        "title": "Resultados-Chave",
        "description": "Um tour guiado pela página de Resultados-Chave — criando resultados mensuráveis, entendendo os tipos de progresso e vinculando Resultados-Chave a Objetivos.",
        "steps": {
            1: {
                "title": "Resultados-Chave",
                "description": "A página de Resultados-Chave lista todos os Resultados-Chave definidos no sistema — os resultados mensuráveis que determinam se um Objetivo foi alcançado. Cada Resultado-Chave tem um tipo de progresso, um valor-alvo e uma duração, e acompanha o progresso real conforme os funcionários atualizam seus valores atuais.",
            },
            2: {
                "title": "Lista de Resultados-Chave",
                "description": "Cada linha mostra um Resultado-Chave — seu título, o tipo de progresso (percentual, número ou moeda), o valor-alvo, a duração e uma descrição. Clique em qualquer linha para abrir a visualização completa de detalhes com o histórico de progresso e os objetivos vinculados.",
            },
            3: {
                "title": "Criar Resultado-Chave",
                "description": "Clique em Criar para definir um novo Resultado-Chave. Defina o título, escolha um tipo de progresso (percentual, número ou moeda), informe o valor-alvo, adicione uma descrição e defina as datas de início e término. O Resultado-Chave pode então ser vinculado a um ou mais Objetivos.",
            },
            4: {
                "title": "Tipos de Progresso",
                "description": "Os Resultados-Chave suportam três tipos de progresso — Percentual (0–100%), Número (qualquer valor numérico, como unidades vendidas ou chamados encerrados) e Moeda (um valor monetário, como receita ou economia de custos). Escolha o tipo que melhor representa o resultado que você está medindo.",
            },
            5: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use os botões de alternância de visualização para trocar entre a visualização em Lista e a visualização em Cartão. A visualização em Cartão oferece uma visão visual compacta de cada Resultado-Chave com suas configurações principais e progresso em um só olhar.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente Resultados-Chave por título ou descrição. A lista é atualizada conforme você digita.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os Resultados-Chave por tipo de progresso, faixa de valor-alvo, duração ou status ativo.",
            },
        },
    },
    "employee-bonus-point-tour": {
        "title": "Pontos de Bônus do Funcionário",
        "description": "Um tour guiado pela página de Pontos de Bônus do Funcionário — concedendo pontos aos funcionários, entendendo como os pontos são acompanhados e como podem ser convertidos em dinheiro pela folha de pagamento.",
        "steps": {
            1: {
                "title": "Pontos de Bônus do Funcionário",
                "description": "A página de Pontos de Bônus do Funcionário acompanha os pontos de bônus concedidos aos funcionários — um sistema de reconhecimento e incentivo ao desempenho. Os pontos podem ser concedidos com base em objetivos alcançados, feedback recebido ou qualquer critério personalizado, e podem depois ser convertidos em dinheiro pelo módulo de Reembolsos.",
            },
            2: {
                "title": "Lista de Pontos de Bônus",
                "description": "Cada linha mostra a entrada de pontos de bônus de um funcionário — o nome do funcionário, o número de pontos de bônus concedidos e em que os pontos se baseiam (o motivo ou critério). Clique em qualquer linha para editar ou excluir a entrada.",
            },
            3: {
                "title": "Conceder Pontos de Bônus",
                "description": "Clique em Criar para conceder pontos de bônus a um funcionário. Selecione o funcionário, informe o número de pontos e especifique em que os pontos se baseiam — por exemplo, um objetivo alcançado, um ciclo de feedback concluído ou uma concessão personalizada.",
            },
            4: {
                "title": "Conversão de Pontos em Dinheiro",
                "description": "Os pontos de bônus acumulados podem ser convertidos em um pagamento monetário pelo módulo de Reembolsos. Depois que um funcionário solicita a conversão, o valor equivalente é adicionado automaticamente ao próximo holerite dele.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente registros de pontos de bônus por nome do funcionário. A lista é atualizada conforme você digita.",
            },
        },
    },
    "period-tour": {
        "title": "Período",
        "description": "Um tour guiado pela página de Período — criando e gerenciando os intervalos de tempo usados para delimitar ciclos de OKR, objetivos e avaliações de desempenho.",
        "steps": {
            1: {
                "title": "Período",
                "description": "A página de Período define os intervalos de tempo usados para os ciclos de OKR e avaliação de desempenho — por exemplo, T1 2024, S1 2025 ou Anual 2024. Cada período tem uma data de início e término. Objetivos, Resultados-Chave e ciclos de feedback são delimitados a esses períodos para que o progresso possa ser acompanhado dentro de um intervalo de tempo definido.",
            },
            2: {
                "title": "Lista de Períodos",
                "description": "Cada linha mostra um período definido — seu nome, data de início e data de término. Clique em qualquer linha para abrir os detalhes completos do período, onde você pode ver todos os objetivos vinculados a ele.",
            },
            3: {
                "title": "Criar Período",
                "description": "Clique em Criar para definir um novo período de desempenho. Dê a ele um nome descritivo (por exemplo, T2 2025), defina as datas de início e término, e salve. Objetivos e Resultados-Chave podem então ser delimitados a este período quando forem criados.",
            },
            4: {
                "title": "Editar e Excluir",
                "description": "Clique em qualquer linha de período para ver seus detalhes. Use a ação Editar para atualizar o nome ou as datas, ou Excluir para removê-lo. Excluir um período não exclui os objetivos vinculados a ele — eles simplesmente perdem a associação com o período.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente períodos por nome. A lista é atualizada conforme você digita.",
            },
        },
    },
    "question-template-tour": {
        "title": "Modelo de Pergunta",
        "description": "Um tour guiado pela página de Modelo de Pergunta — criando conjuntos reutilizáveis de perguntas de avaliação que podem ser anexados a ciclos de feedback e reuniões.",
        "steps": {
            1: {
                "title": "Modelo de Pergunta",
                "description": "Modelos de Pergunta são conjuntos reutilizáveis de perguntas de avaliação usados em ciclos de Feedback e Reunião. Em vez de digitar perguntas do zero a cada vez, você define um modelo uma vez e o anexa a qualquer ciclo de feedback ou reunião — mantendo seu processo de avaliação consistente em toda a organização.",
            },
            2: {
                "title": "Lista de Modelos",
                "description": "Cada linha mostra um modelo de pergunta — seu título e o número total de perguntas que contém. Clique em qualquer linha para abrir a página de detalhes do modelo, onde você pode visualizar, adicionar ou editar perguntas individuais.",
            },
            3: {
                "title": "Criar Modelo",
                "description": "Clique em Criar para definir um novo modelo de pergunta. Dê a ele um título descritivo e salve. Você pode então abrir o modelo para adicionar perguntas — cada pergunta pode ser de resposta em texto, avaliação, sim/não ou múltipla escolha.",
            },
            4: {
                "title": "Adicionando Perguntas",
                "description": "Clique em qualquer linha de modelo para abrir sua página de detalhes. A partir dali você pode adicionar, editar ou reordenar as perguntas. Cada pergunta tem um tipo — texto curto, texto longo, escala de avaliação, sim/não ou múltipla escolha — e pode ser marcada como obrigatória.",
            },
            5: {
                "title": "Usando Modelos",
                "description": "Depois de criados, os modelos de pergunta podem ser anexados a ciclos de Feedback ou Reuniões. Quando um avaliador abre seu feedback ou reunião atribuídos, as perguntas do modelo aparecem automaticamente para ele responder.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente modelos de pergunta por título. A lista é atualizada conforme você digita.",
            },
        },
    },
    "exit-process-tour": {
        "title": "Processo de Saída",
        "description": "Um tour guiado pela página de Processo de Saída — configurando fluxos de desligamento, gerenciando etapas, atribuindo funcionários e acompanhando tarefas até a quitação final.",
        "steps": {
            1: {
                "title": "Processo de Saída",
                "description": "A página de Processo de Saída gerencia o desligamento de funcionários por meio de um fluxo estruturado. Cada fluxo que você define representa um processo específico de desligamento — por exemplo, um desligamento do departamento de TI ou uma saída definitiva — com etapas personalizadas pelas quais os funcionários passam desde o último dia até a quitação.",
            },
            2: {
                "title": "Visualização do Fluxo",
                "description": "A área do fluxo mostra todos os processos de desligamento ativos como abas. Selecione uma aba para ver as etapas daquele fluxo e os funcionários atualmente em cada etapa. Use a visualização em lista para um layout de tabela compacto ou alterne para a visualização em cartão para um quadro kanban visual.",
            },
            3: {
                "title": "Abas do Fluxo",
                "description": "Cada aba no topo representa um fluxo de desligamento — por exemplo, Desligamento de TI ou Saída Completa. Clique em uma aba para carregar suas etapas e ver os funcionários que estão atualmente passando por aquele fluxo.",
            },
            4: {
                "title": "Ações do Fluxo",
                "description": "Cada aba de fluxo tem um menu Ações. Use-o para adicionar uma nova etapa ao fluxo, gerenciar a ordem das etapas, atualizar as configurações do fluxo ou excluí-lo.",
            },
            5: {
                "title": "Criar Fluxo de Desligamento",
                "description": "Clique em Criar para definir um novo fluxo de desligamento. Dê a ele um título, defina os administradores responsáveis e configure se ele está ativo. Depois de criado, você pode adicionar etapas a ele e começar a atribuir os funcionários que estão passando por aquele processo de desligamento.",
            },
            6: {
                "title": "Etapas do Fluxo",
                "description": "Cada fluxo é dividido em etapas — passos sequenciais pelos quais um funcionário passa durante o desligamento, como Aviso Prévio, Documentação, Devolução de Ativos e Quitação Final. Você pode adicionar, reordenar e editar as etapas pelo menu Ações da etapa. As etapas são exibidas como colunas na visualização em cartão ou como seções agrupadas na visualização em lista.",
            },
            7: {
                "title": "Adicionando Funcionários",
                "description": "Para iniciar o desligamento de um funcionário, clique em Adicionar Funcionário na etapa relevante do fluxo. Selecione o funcionário e defina o último dia de trabalho e a data final do aviso prévio. O registro do funcionário aparece então naquela etapa e avança conforme o desligamento progride.",
            },
            8: {
                "title": "Tarefas e Observações do Funcionário",
                "description": "Cada funcionário no fluxo pode receber tarefas — ações específicas que ele ou o RH devem concluir antes de avançar para a próxima etapa, como devolver equipamentos ou assinar documentos. Você também pode adicionar observações e enviar e-mails diretamente do cartão de desligamento do funcionário.",
            },
            9: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Use a alternância de visualização para trocar entre a visualização em Lista (uma tabela compacta de funcionários agrupados por etapa) e a visualização em Cartão (um quadro kanban visual com movimentação de etapa por arrastar e soltar). Ambas as visualizações mostram os mesmos dados — escolha o layout que melhor se adapta ao seu fluxo de trabalho.",
            },
            10: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a visualização do fluxo por fluxo de desligamento, etapa, funcionário, departamento, cargo ou datas de aviso prévio. Os filtros são combinados — você pode acumular vários critérios para focar exatamente nos funcionários que precisa.",
            },
        },
    },
    "asset-category-tour": {
        "title": "Categoria de Ativos",
        "description": "Um tour guiado pela página de Categoria de Ativos — organizando ativos em categorias, adicionando ativos dentro de cada categoria e gerenciando o inventário por tipo.",
        "steps": {
            1: {
                "title": "Categoria de Ativos",
                "description": "A página de Categoria de Ativos organiza os ativos da sua empresa em grupos lógicos — por exemplo, Notebooks, Mobiliário, Veículos ou Equipamentos de TI. Cada categoria funciona como um contêiner para ativos individuais, facilitando o rastreamento do inventário, a geração de relatórios e o gerenciamento de atribuições por tipo.",
            },
            2: {
                "title": "Lista de Categorias",
                "description": "Cada linha representa uma categoria de ativos. O indicador mostra quantos ativos há naquela categoria. Clique em qualquer linha para expandi-la e ver os ativos individuais dentro dela — seus IDs de rastreamento, status, funcionário designado e detalhes de compra.",
            },
            3: {
                "title": "Criar Categoria",
                "description": "Clique em Criar para adicionar uma nova categoria de ativos. Informe um nome e uma descrição opcional. Depois que a categoria existir, você pode começar a adicionar ativos individuais a ela.",
            },
            4: {
                "title": "Ativos Dentro de uma Categoria",
                "description": "Clique em qualquer linha de categoria para expandi-la e ver todos os ativos naquele grupo. Cada entrada de ativo mostra o ID de rastreamento, status (Em Uso, Disponível, Danificado etc.), o funcionário designado e a data de compra. Clique na linha de um ativo para abrir sua visualização completa de detalhes.",
            },
            5: {
                "title": "Ações da Categoria",
                "description": "Cada linha de categoria tem um menu Ações — use-o para Adicionar um Ativo àquela categoria, Editar o nome ou a descrição da categoria, Duplicar a estrutura da categoria ou Excluí-la. Excluir uma categoria não exclui os ativos dentro dela — eles precisarão ser reatribuídos.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente uma categoria ou ativo por nome ou ID de rastreamento. A lista é atualizada conforme você digita.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por nome da categoria, nome do ativo, ID de rastreamento, data de compra, custo de compra, número do lote, categoria ou status. Você também pode importar ativos em massa ou exportar a lista completa de ativos nas opções Importar e Exportar ao lado do botão Criar.",
            },
        },
    },
    "asset-batch-number-tour": {
        "title": "Número do Lote de Ativos",
        "description": "Um tour guiado pela página de Número do Lote de Ativos — criando números de lote, vinculando ativos a um lote e visualizando os detalhes do lote.",
        "steps": {
            1: {
                "title": "Número do Lote de Ativos",
                "description": "A página de Número do Lote de Ativos gerencia os números de lote dos ativos — identificadores únicos usados para agrupar ativos que foram comprados ou recebidos juntos. Rastrear ativos por lote facilita o gerenciamento de garantias, devoluções e auditorias para todo um grupo de compra de uma vez.",
            },
            2: {
                "title": "Lista de Lotes",
                "description": "Cada linha mostra um lote de ativos — o número do lote, o número de ativos vinculados a ele e uma descrição opcional. Clique em qualquer linha para abrir a visualização de detalhes do lote, mostrando todos os ativos pertencentes a ele.",
            },
            3: {
                "title": "Criar Número de Lote",
                "description": "Clique em Criar para definir um novo lote de ativos. Informe um número de lote único e uma descrição opcional. Depois de criado, os ativos podem ser atribuídos a este lote quando forem adicionados ao sistema.",
            },
            4: {
                "title": "Detalhe do Lote",
                "description": "Clique em qualquer linha de lote para abrir sua visualização de detalhes. Você pode ver todos os ativos pertencentes a esse lote — seus nomes, categorias, status e funcionários designados. Use esta visualização para gerenciar garantias ou devoluções de todo um grupo de compra.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente um lote por número ou descrição. A lista é atualizada conforme você digita.",
            },
        },
    },
    "asset-section-tour": {
        "title": "Ativo",
        "description": "Um tour guiado pela página de Ativo — visualizando ativos atribuídos, abrindo solicitações, gerenciando alocações e processando devoluções.",
        "steps": {
            1: {
                "title": "Ativo",
                "description": "A página de Ativo é o centro de rastreamento de atribuições, solicitações e alocações de ativos em toda a organização. Os funcionários podem ver os ativos atribuídos a eles e abrir solicitações aqui, enquanto os administradores podem gerenciar todas as alocações e aprovações.",
            },
            2: {
                "title": "Aba Ativo",
                "description": "A aba Ativo mostra todos os ativos atualmente atribuídos a você. Cada linha exibe o nome do ativo, categoria, ID de rastreamento, número do lote, data de atribuição e status atual. Clique em qualquer linha para ver o detalhe completo do ativo, incluindo a descrição e as informações de quem atribuiu.",
            },
            3: {
                "title": "Aba Solicitação de Ativo",
                "description": "A aba Solicitação de Ativo lista todas as solicitações de ativo — as suas como funcionário, e as solicitações dos seus subordinados como administrador. Os administradores podem aprovar ou rejeitar solicitações diretamente nesta aba. Use a ação Criar Solicitação no menu da aba para abrir uma nova solicitação de ativo.",
            },
            4: {
                "title": "Aba Alocação de Ativo",
                "description": "A aba Alocação de Ativo mostra todos os registros de alocação — quais ativos foram atribuídos a quais funcionários, em que data e com qual data de devolução prevista. Os administradores podem criar novas alocações, renovar as existentes ou processar devoluções pelo menu de ações da aba.",
            },
            5: {
                "title": "Lista de Registros",
                "description": "A lista de registros é atualizada quando você troca de aba — mostrando seus ativos, solicitações ou alocações dependendo da aba ativa. Clique em qualquer linha para abrir uma visualização detalhada daquele ativo, solicitação ou registro de alocação.",
            },
            6: {
                "title": "Ações da Aba",
                "description": "Cada aba tem um menu Ações com operações relevantes para aquela aba — Criar Solicitação na aba Solicitação de Ativo, e Criar Alocação ou Renovação de Ativo na aba Alocação de Ativo. Clique no botão Ações ao lado da aba ativa para ver as opções disponíveis.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente um ativo, solicitação ou alocação pelo nome do funcionário, nome do ativo ou ID de rastreamento. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por categoria de ativo, funcionário, departamento, data de atribuição, data de devolução ou status da solicitação. Os filtros se aplicam à aba atualmente ativa.",
            },
        },
    },
    "asset-history-tour": {
        "title": "Histórico de Ativos",
        "description": "Um tour guiado pela página de Histórico de Ativos — revisando o registro completo de auditoria de atribuições, devoluções e status de ativos em toda a organização.",
        "steps": {
            1: {
                "title": "Histórico de Ativos",
                "description": "A página de Histórico de Ativos fornece um registro completo de auditoria de todas as atribuições de ativos na organização — mostrando quais ativos foram atribuídos a quais funcionários, quando foram atribuídos, quando foram devolvidos e o status da devolução. É a visualização de referência para rastrear o ciclo de vida de um ativo.",
            },
            2: {
                "title": "Lista de Histórico",
                "description": "Cada linha mostra um registro de atribuição — o nome do ativo, o funcionário a quem foi atribuído, a data de atribuição, a data de devolução e o status da devolução (devolvido, danificado ou ainda ativo). Clique em qualquer linha para abrir o detalhe completo da atribuição.",
            },
            3: {
                "title": "Detalhe da Atribuição",
                "description": "Clicar em uma linha abre o detalhe da atribuição do ativo — mostrando o ID de rastreamento, número do lote, data de atribuição, status da devolução, funcionário que atribuiu e descrição do ativo. Use isso para investigar o histórico completo de um ativo ou atribuição específica.",
            },
            4: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar rapidamente registros de histórico por nome do ativo ou nome do funcionário. A lista é atualizada conforme você digita.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros de histórico por ativo, funcionário, departamento, intervalo de data de atribuição, intervalo de data de devolução ou status da devolução. Combine filtros para identificar eventos de atribuição específicos.",
            },
        },
    },
    "faq-categories-tour": {
        "title": "Categorias de Perguntas Frequentes",
        "description": "Um tour guiado pela página de Categorias de Perguntas Frequentes — criando categorias, adicionando perguntas, gerenciando conteúdo e ajudando os funcionários a encontrar respostas rapidamente.",
        "steps": {
            1: {
                "title": "Categorias de Perguntas Frequentes",
                "description": "A página de Categorias de Perguntas Frequentes organiza as Perguntas Frequentes da sua empresa em grupos por tópico. Os funcionários podem pesquisar e navegar pelas Perguntas Frequentes aqui para encontrar respostas sem precisar abrir um chamado de suporte. Os administradores gerenciam as categorias e as perguntas de cada uma.",
            },
            2: {
                "title": "Cartões de Categoria",
                "description": "Cada cartão representa uma categoria de Perguntas Frequentes — mostrando seu título e as perguntas que contém. Clique em um cartão de categoria para expandi-lo e ler as Perguntas Frequentes daquele tópico. As categorias mantêm perguntas relacionadas agrupadas para que os funcionários possam navegar por assunto.",
            },
            3: {
                "title": "Criar Categoria",
                "description": "Clique em Criar para adicionar uma nova categoria de Perguntas Frequentes. Dê a ela um título claro que descreva o tópico — por exemplo, Folha de Pagamento, Política de Licenças ou Suporte de TI. Depois de criada, você pode adicionar perguntas individuais a ela.",
            },
            4: {
                "title": "Adicionando Perguntas Frequentes",
                "description": "Clique em Ver Perguntas Frequentes em qualquer cartão de categoria para abri-la e gerenciar suas perguntas. Use o botão Adicionar Pergunta Frequente dentro dela para criar uma nova pergunta e uma resposta em texto formatado. Você pode adicionar quantas Perguntas Frequentes forem necessárias dentro de uma categoria.",
            },
            5: {
                "title": "Ações da Categoria",
                "description": "Cada cartão de categoria tem um menu de ações — clique no ícone de três pontos no cartão para Editar o título da categoria ou Excluí-la. Excluir uma categoria remove todas as Perguntas Frequentes dentro dela, então certifique-se de reatribuir ou anotar qualquer conteúdo importante antes de excluir.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar Perguntas Frequentes por palavra-chave em todas as categorias. Conforme você digita, as perguntas correspondentes são sugeridas — selecione uma para ir direto à resposta. Esta é a forma mais rápida para os funcionários encontrarem respostas por conta própria.",
            },
        },
    },
    "tickets-tour": {
        "title": "Chamados",
        "description": "Um tour guiado pelo quadro de chamados da Central de Ajuda — abrindo chamados, acompanhando o status pelo fluxo, gerenciando atribuições e usando filtros para ficar em dia com as solicitações abertas.",
        "steps": {
            1: {
                "title": "Chamados",
                "description": "A página de Chamados é um quadro estilo kanban de central de ajuda onde os funcionários abrem solicitações de suporte e os administradores acompanham a resolução. Os chamados são organizados em colunas de status — Novo, Em Andamento, Resolvido e assim por diante — para que toda a equipe veja o que está aberto, o que está sendo trabalhado e o que foi concluído.",
            },
            2: {
                "title": "Fluxo de Chamados",
                "description": "O quadro do fluxo mostra os chamados como cartões organizados em colunas de status. Arraste um cartão de chamado de uma coluna para outra para atualizar seu status instantaneamente. Clique em qualquer cartão para abrir o detalhe completo do chamado — incluindo a descrição, anexos, agente designado e registro de atividades.",
            },
            3: {
                "title": "Meus Chamados",
                "description": "A aba Meus Chamados mostra apenas os chamados que você abriu. Use esta aba para acompanhar o status das suas próprias solicitações de suporte e fazer follow-up de chamados que estão aguardando sua resposta.",
            },
            4: {
                "title": "Chamados Sugeridos",
                "description": "A aba Chamados Sugeridos apresenta chamados relevantes para você com base na sua função, departamento ou área de conhecimento — chamados que você pode ajudar a resolver mesmo que não tenham sido atribuídos diretamente a você.",
            },
            5: {
                "title": "Todos os Chamados",
                "description": "A aba Todos os Chamados dá aos administradores e à equipe da central de ajuda uma visão completa de todos os chamados do sistema, independentemente de quem os abriu ou a quem foram atribuídos. Use esta aba para monitorar a carga de trabalho geral, reatribuir chamados e garantir que nada passe despercebido.",
            },
            6: {
                "title": "Criar Chamado",
                "description": "Clique em Criar para abrir um novo chamado de suporte. Preencha o título, selecione o tipo e a prioridade do chamado, adicione uma descrição e, opcionalmente, anexe arquivos. O chamado aparece imediatamente no quadro, na coluna Novo, e fica visível para a equipe responsável.",
            },
            7: {
                "title": "Ações de Chamado",
                "description": "O menu Ações permite que os administradores realizem operações em massa nos chamados selecionados — Arquivar chamados encerrados para manter o quadro organizado, Desarquivar chamados que precisam ser reabertos, ou Excluir chamados criados por erro.",
            },
            8: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Alterne entre a visualização em Cartão (kanban) e a visualização em Lista (tabular) usando o alternador de visualização. A visualização em cartão é ideal para visualizar o fluxo de trabalho entre status; a visualização em lista é melhor para ordenar e revisar muitos chamados de uma vez.",
            },
            9: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os chamados por status, prioridade, tipo de chamado, agente designado, departamento, funcionário que abriu ou intervalo de datas. Combine filtros para focar exatamente nos chamados que você precisa revisar.",
            },
        },
    },
    "projects-tour": {
        "title": "Projetos",
        "description": "Um tour guiado pela página de Projetos — criando projetos, gerenciando tarefas e marcos, acompanhando o progresso e usando filtros para ficar em dia com o trabalho da sua equipe.",
        "steps": {
            1: {
                "title": "Projetos",
                "description": "A página de Projetos é o centro de gerenciamento de trabalho em toda a organização. Os administradores de projeto podem criar projetos, atribuir membros da equipe, definir marcos e acompanhar o progresso — enquanto os membros da equipe podem ver os projetos dos quais fazem parte e monitorar suas tarefas.",
            },
            2: {
                "title": "Lista de Projetos",
                "description": "Cada linha ou cartão representa um projeto — mostrando o nome do projeto, administradores designados, membros, datas de início e término, e status atual. Clique em qualquer projeto para abrir sua página de detalhes, onde você pode gerenciar tarefas, marcos, membros e atividades.",
            },
            3: {
                "title": "Criar Projeto",
                "description": "Clique em Criar para iniciar um novo projeto. Informe o nome do projeto, a descrição, selecione administradores e membros, defina as datas de início e término e escolha o status inicial. Depois de criado, o projeto aparece na lista e você pode começar a adicionar tarefas e marcos.",
            },
            4: {
                "title": "Detalhe do Projeto",
                "description": "Clicar em um projeto abre sua página de detalhes. Aqui você pode gerenciar as tarefas do projeto, definir marcos, revisar o registro de atividades, atualizar membros e acompanhar o percentual de conclusão geral. Todo o trabalho do projeto — atribuição, atualizações de progresso e comentários — acontece dentro da visualização de detalhes.",
            },
            5: {
                "title": "Ações do Projeto",
                "description": "O menu Ações oferece operações em massa e de dados — Importar projetos de um arquivo, Exportar a lista, Arquivar projetos concluídos ou inativos para manter a visualização organizada, Desarquivar projetos que precisam ser reativados, ou Excluir projetos que não são mais necessários.",
            },
            6: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Alterne entre a visualização em Lista (tabular) e a visualização em Cartão (visual) usando o alternador de visualização. A visualização em lista é melhor para revisar muitos projetos e ordenar por data ou status; a visualização em cartão oferece uma visão mais visual de cada projeto em um só olhar.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar um projeto por nome. A lista é atualizada conforme você digita, facilitando localizar um projeto específico quando você tem muitos projetos ativos.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista de projetos por administrador, membro da equipe, status, estado ativo ou intervalo de datas. Combine filtros para focar nos projetos mais relevantes para você — por exemplo, todos os projetos ativos que você gerencia e que terminam neste trimestre.",
            },
        },
    },
    "tasks-tour": {
        "title": "Tarefas",
        "description": "Um tour guiado pela página de Tarefas — criando e acompanhando tarefas em todos os projetos, gerenciando status e atribuições, e usando filtros para focar no trabalho mais importante.",
        "steps": {
            1: {
                "title": "Tarefas",
                "description": "A página de Tarefas oferece uma visão consolidada de todas as tarefas de cada projeto do qual você faz parte. Você pode criar tarefas independentes, acompanhar o progresso por status e filtrar entre projetos, etapas e membros da equipe — tudo sem precisar abrir as páginas individuais de cada projeto.",
            },
            2: {
                "title": "Lista de Tarefas",
                "description": "Cada linha mostra uma tarefa — o título da tarefa, o projeto ao qual pertence, sua etapa atual, os membros designados, a prioridade, a data de vencimento e o status de conclusão. Um indicador de cor mostra rapidamente se a tarefa está A Fazer, Em Andamento, Concluída ou Expirada.",
            },
            3: {
                "title": "Criar Tarefa",
                "description": "Clique em Criar para adicionar uma nova tarefa. Preencha o título, selecione o projeto e a etapa, atribua membros da equipe, defina a prioridade e a data de vencimento, e adicione uma descrição. Depois de salva, a tarefa aparece na lista e fica visível para todos os membros designados.",
            },
            4: {
                "title": "Detalhe da Tarefa",
                "description": "Clique em qualquer linha de tarefa para abrir sua visualização de detalhes. Aqui você pode atualizar o status, reatribuir membros, adicionar subtarefas, registrar comentários e acompanhar o histórico de atividades daquela tarefa. A visualização de detalhes é onde o trabalho do dia a dia em uma tarefa é registrado.",
            },
            5: {
                "title": "Ações da Tarefa",
                "description": "O menu Ações oferece operações em massa nas tarefas selecionadas — Arquivar tarefas que estão concluídas, mas precisam ser mantidas para referência, Desarquivar tarefas que precisam voltar à visualização ativa, ou Excluir tarefas que não são mais relevantes.",
            },
            6: {
                "title": "Visualizações em Lista e Cartão",
                "description": "Alterne entre a visualização em Lista (tabular) e a visualização em Cartão (visual). A visualização em lista é melhor para ordenar e revisar muitas tarefas; a visualização em cartão apresenta cada tarefa como um bloco visual, facilitando uma visão rápida da carga de trabalho da equipe.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar tarefas por título. A lista é atualizada conforme você digita, facilitando localizar uma tarefa específica em todos os seus projetos sem precisar rolar a tela.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir as tarefas por projeto, etapa, status, prioridade, membro designado ou intervalo de data de vencimento. Use a opção Agrupar Por para reorganizar a lista por projeto, etapa ou status para uma visão estruturada da distribuição da carga de trabalho.",
            },
        },
    },
    "timesheets-tour": {
        "title": "Folhas de Horas",
        "description": "Um tour guiado pela página de Folhas de Horas — registrando entradas de tempo, revisando e aprovando folhas de horas, e analisando a distribuição da carga de trabalho entre projetos e funcionários.",
        "steps": {
            1: {
                "title": "Folhas de Horas",
                "description": "A página de Folhas de Horas é onde os funcionários registram o tempo que dedicam às tarefas de projeto. Os administradores podem revisar todos os registros de tempo da equipe, acompanhar horas por projeto ou funcionário, e monitorar a distribuição da carga de trabalho. Cada registro vincula uma data, um projeto, uma tarefa e o tempo dedicado a um funcionário.",
            },
            2: {
                "title": "Lista de Folhas de Horas",
                "description": "Cada linha mostra um registro de tempo — o funcionário, o projeto, a tarefa, a data, o tempo dedicado e o status atual (Solicitado, Aprovado ou Rejeitado). Clique em qualquer linha para abrir o detalhe completo da folha de horas, incluindo a descrição do trabalho realizado.",
            },
            3: {
                "title": "Registrar Tempo",
                "description": "Clique em Criar para registrar uma nova entrada de tempo. Selecione o projeto e a tarefa, informe a data e o tempo dedicado, adicione uma descrição do trabalho realizado e envie. O registro é criado com o status Solicitado e pode ser aprovado por um administrador.",
            },
            4: {
                "title": "Detalhe da Folha de Horas",
                "description": "Clique em qualquer linha de folha de horas para abrir sua visualização de detalhes. Aqui você pode revisar todas as informações daquele registro, atualizar o status (Aprovar ou Rejeitar), e ler a descrição do trabalho concluído. Os administradores usam esta visualização para revisar e agir sobre entradas de tempo individuais.",
            },
            5: {
                "title": "Excluir Registros",
                "description": "Selecione uma ou mais linhas de folha de horas e use o menu Ações para excluir registros em massa. Use isso para remover entradas duplicadas ou registradas incorretamente antes de serem revisadas.",
            },
            6: {
                "title": "Visualizações em Lista, Cartão e Gráfico",
                "description": "Alterne entre visualizações usando o alternador. A visualização em Lista mostra todos os registros em uma tabela ordenável; a visualização em Cartão apresenta cada registro como um bloco; a visualização em Gráfico oferece um detalhamento visual do tempo dedicado por funcionário ou projeto — útil para análise de carga de trabalho e relatórios.",
            },
            7: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar registros de folha de horas por nome do funcionário ou título da tarefa. A lista é atualizada conforme você digita.",
            },
            8: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros por projeto, tarefa, funcionário, status ou intervalo de datas. Use a opção Agrupar Por para reorganizar os registros por funcionário, projeto, data, departamento ou administrador responsável para relatórios estruturados.",
            },
        },
    },
    "employee-report-tour": {
        "title": "Relatório de Funcionários",
        "description": "Um tour guiado pela página de Relatório de Funcionários — construindo tabelas dinâmicas para analisar dados da força de trabalho por departamento, função e mais, e exportando os resultados para o Excel.",
        "steps": {
            1: {
                "title": "Relatório de Funcionários",
                "description": "A página de Relatório de Funcionários oferece uma tabela dinâmica interativa para analisar os dados da sua força de trabalho. Segmente e agrupe funcionários por departamento, função, cargo, turno, tipo de trabalho e mais — depois alterne para gráficos para obter percepções visuais. Todos os dados podem ser exportados para o Excel.",
            },
            2: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica é o coração do relatório. Ela agrega os dados dos funcionários com base nas linhas e colunas que você configurar. Por padrão, ela agrupa por Departamento, Cargo e Função — mas você pode arrastar qualquer campo disponível para a área de linhas ou colunas para reformular a visualização instantaneamente.",
            },
            3: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Soma, Média) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor, Gráfico de Dispersão) nas listas suspensas para alterar como os dados são resumidos e exibidos.",
            },
            4: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os dados de funcionários que alimentam a tabela dinâmica. Filtre por nome, e-mail, empresa, departamento, função, cargo, turno, tipo de trabalho, tipo de funcionário, administrador responsável, gênero, país ou telefone antes que a tabela dinâmica os processe.",
            },
            5: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel. A exportação inclui os detalhes da sua empresa e um registro de data e hora. O botão Exportar só é visível quando um renderizador de tabela (Tabela, Mapa de Calor etc.) está ativo — ele é ocultado automaticamente quando um renderizador de gráfico é selecionado.",
            },
        },
    },
    "recruitment-report-tour": {
        "title": "Relatório de Recrutamento",
        "description": "Um tour guiado pela página de Relatório de Recrutamento — analisando candidatos, processos de recrutamento e etapas de integração com uma tabela dinâmica interativa e exportação para Excel.",
        "steps": {
            1: {
                "title": "Relatório de Recrutamento",
                "description": "A página de Relatório de Recrutamento oferece uma tabela dinâmica interativa para analisar seu fluxo de contratação. Você pode gerar relatórios em três conjuntos de dados — Candidatos, Processos de Recrutamento e Etapas de Integração — facilitando o acompanhamento das taxas de conversão, duração das etapas e tendências de contratação.",
            },
            2: {
                "title": "Selecionar Modelo de Dados",
                "description": "Use a lista suspensa de seleção de modelo para escolher qual conjunto de dados analisar — Candidato, Recrutamento ou Etapa de Integração. Cada modelo expõe campos diferentes na tabela dinâmica, então alterne entre eles para responder a diferentes perguntas sobre seu processo de recrutamento.",
            },
            3: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados do modelo selecionado com base nas linhas e colunas que você configurar. Arraste campos para as áreas de linha ou coluna e escolha uma agregação e um renderizador para reformular a visualização. Alterne para um Gráfico de Barras ou Gráfico de Dispersão para análise visual de tendências.",
            },
            4: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Soma, Média) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados de contratação são resumidos e exibidos.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir o conjunto de dados que alimenta a tabela dinâmica. Filtre candidatos por etapa, habilidade, origem ou data de admissão; filtre processos de recrutamento por cargo e data; filtre etapas de integração por fluxo e status — depois execute novamente a tabela dinâmica no subconjunto filtrado.",
            },
            6: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. O botão fica visível apenas quando um renderizador do tipo tabela está ativo.",
            },
        },
    },
    "attendance-report-tour": {
        "title": "Relatório de Presença",
        "description": "Um tour guiado pela página de Relatório de Presença — construindo tabelas dinâmicas para analisar padrões de presença por funcionário, departamento e data, e exportando os resultados para o Excel.",
        "steps": {
            1: {
                "title": "Relatório de Presença",
                "description": "A página de Relatório de Presença oferece uma tabela dinâmica interativa para analisar os registros de presença em toda a organização. Agrupe e agregue por funcionário, departamento, turno, data, horário de entrada e mais para identificar padrões, atrasos ou tendências de absenteísmo.",
            },
            2: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados de presença com base nas linhas e colunas que você configurar. Por padrão, ela agrupa por funcionário e data — mas você pode arrastar qualquer campo disponível para a área de linhas ou colunas para reformular a análise. Alterne os renderizadores para ver Gráficos de Barras ou Mapas de Calor para padrões visuais.",
            },
            3: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Soma de horas, Média) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados de presença são resumidos e exibidos.",
            },
            4: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros de presença que alimentam a tabela dinâmica. Filtre por funcionário, departamento, turno, empresa, cargo, tipo de trabalho, intervalo de data de presença, horário de entrada, horário de saída ou status de presença em lote.",
            },
            5: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. O botão fica visível apenas quando um renderizador do tipo tabela está ativo — ele é ocultado automaticamente quando um renderizador de gráfico é selecionado.",
            },
        },
    },
    "leave-report-tour": {
        "title": "Relatório de Licenças",
        "description": "Um tour guiado pela página de Relatório de Licenças — analisando solicitações de licença e saldos de licença disponíveis com uma tabela dinâmica interativa e exportação para Excel.",
        "steps": {
            1: {
                "title": "Relatório de Licenças",
                "description": "A página de Relatório de Licenças oferece uma tabela dinâmica interativa para analisar os dados de licença em toda a organização. Você pode gerar relatórios em dois conjuntos de dados — Solicitações de Licença e Licença Disponível — para acompanhar utilização, saldos e tendências por funcionário, departamento ou tipo de licença.",
            },
            2: {
                "title": "Selecionar Modelo de Dados",
                "description": "Use a lista suspensa de seleção de modelo para escolher qual conjunto de dados analisar — Solicitação de Licença (pedidos de licença enviados e aprovados) ou Licença Disponível (saldos de licença atuais por funcionário). Cada modelo expõe campos diferentes na tabela dinâmica.",
            },
            3: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados do modelo selecionado com base nas linhas e colunas que você configurar. Arraste campos para as áreas de linha ou coluna para reformular a visualização — por exemplo, agrupe solicitações de licença por departamento e tipo de licença para ver quais equipes tiram mais licença.",
            },
            4: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Soma de dias) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados de licença são resumidos e exibidos.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir o conjunto de dados que alimenta a tabela dinâmica. Filtre solicitações de licença por funcionário, departamento, tipo de licença, status, intervalo de datas, datas solicitadas ou dias solicitados — depois execute novamente a tabela dinâmica no subconjunto filtrado.",
            },
            6: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. O botão fica visível apenas quando um renderizador do tipo tabela está ativo.",
            },
        },
    },
    "payroll-report-tour": {
        "title": "Relatório de Folha de Pagamento",
        "description": "Um tour guiado pela página de Relatório de Folha de Pagamento — analisando holerites e detalhamentos de rubricas com uma tabela dinâmica interativa e exportação para Excel.",
        "steps": {
            1: {
                "title": "Relatório de Folha de Pagamento",
                "description": "A página de Relatório de Folha de Pagamento oferece uma tabela dinâmica interativa para analisar os dados da folha de pagamento. Você pode gerar relatórios em dois conjuntos de dados — Holerites e detalhamentos de Auxílio ou Dedução — para acompanhar a distribuição salarial, os totais das rubricas e as tendências da folha de pagamento entre departamentos e períodos.",
            },
            2: {
                "title": "Selecionar Modelo de Dados",
                "description": "Use a lista suspensa de seleção de modelo para escolher qual conjunto de dados analisar — Holerite (salário líquido geral, salário básico, deduções por funcionário) ou Auxílio/Dedução (itens individuais de rubrica). Trocar de modelo atualiza a tabela dinâmica com os campos relevantes.",
            },
            3: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados da folha de pagamento com base nas linhas e colunas que você configurar. Por exemplo, agrupe holerites por departamento e mês para ver o gasto total da folha de pagamento por equipe ao longo do tempo, ou detalhe por rubrica para identificar os maiores componentes de custo.",
            },
            4: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Soma, Média, Contagem) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados da folha de pagamento são resumidos e exibidos.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros de folha de pagamento que alimentam a tabela dinâmica. Filtre por funcionário, departamento, datas de início e término do período de pagamento, status do holerite ou faixa salarial — depois execute novamente a tabela dinâmica no subconjunto filtrado.",
            },
            6: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. Use isso para compartilhar resumos da folha de pagamento com as equipes financeiras ou para relatórios de conformidade.",
            },
        },
    },
    "asset-report-tour": {
        "title": "Relatório de Ativos",
        "description": "Um tour guiado pela página de Relatório de Ativos — construindo tabelas dinâmicas para analisar o inventário, a alocação e os dados de custo dos ativos, e exportando os resultados para o Excel.",
        "steps": {
            1: {
                "title": "Relatório de Ativos",
                "description": "A página de Relatório de Ativos oferece uma tabela dinâmica interativa para analisar os dados de ativos em toda a organização. Agrupe e agregue por nome do ativo, categoria, status, funcionário designado, data de compra e custo para acompanhar a utilização, a depreciação e os padrões de alocação de ativos.",
            },
            2: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados de ativos com base nas linhas e colunas que você configurar. Arraste qualquer campo disponível para a área de linhas ou colunas para reformular a análise — por exemplo, agrupe por categoria e status para ver quantos ativos de cada categoria estão em uso, disponíveis ou em manutenção.",
            },
            3: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Soma de custo) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados de ativos são resumidos e exibidos.",
            },
            4: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros de ativos que alimentam a tabela dinâmica. Filtre por nome do ativo, ID de rastreamento, faixa de custo de compra, categoria, status ou intervalo de data de compra — depois execute novamente a tabela dinâmica no subconjunto filtrado.",
            },
            5: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. Use isso para compartilhar resumos de inventário de ativos ou preparar relatórios de auditoria.",
            },
        },
    },
    "pms-report-tour": {
        "title": "Relatório de PMS",
        "description": "Um tour guiado pela página de Relatório de PMS — analisando objetivos, feedback e resultados-chave dos funcionários com uma tabela dinâmica interativa e exportação para Excel.",
        "steps": {
            1: {
                "title": "Relatório de PMS",
                "description": "A página de Relatório de PMS oferece uma tabela dinâmica interativa para analisar os dados do Sistema de Gestão de Desempenho. Você pode gerar relatórios em três conjuntos de dados — Objetivos, Feedback e Resultados-Chave do Funcionário — para acompanhar o progresso das metas, as tendências de feedback e as avaliações de desempenho em toda a organização.",
            },
            2: {
                "title": "Selecionar Modelo de Dados",
                "description": "Use a lista suspensa de seleção de modelo para escolher qual conjunto de dados de desempenho analisar — Objetivo (metas da empresa e individuais), Feedback (entradas de feedback 360°) ou Objetivo do Funcionário (resultados-chave vinculados a um funcionário). Cada modelo expõe campos diferentes na tabela dinâmica.",
            },
            3: {
                "title": "Tabela Dinâmica",
                "description": "A tabela dinâmica agrega os dados do modelo selecionado com base nas linhas e colunas que você configurar. Por exemplo, agrupe objetivos por departamento e status para ver as taxas de conclusão de metas por equipe, ou agrupe feedback por avaliador e avaliação para identificar padrões de desempenho.",
            },
            4: {
                "title": "Linhas, Colunas e Agregação",
                "description": "Use os botões de campo no topo da tabela dinâmica para arrastar atributos para Linhas ou Colunas. Escolha uma Agregação (Contagem, Média de avaliação) e um Renderizador (Tabela, Gráfico de Barras, Mapa de Calor) nas listas suspensas para alterar como os dados de desempenho são resumidos e exibidos.",
            },
            5: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir os registros de PMS que alimentam a tabela dinâmica. Filtre objetivos por funcionário, departamento ou administrador; filtre feedback por avaliador, funcionário ou período — depois execute novamente a tabela dinâmica no subconjunto filtrado.",
            },
            6: {
                "title": "Exportar para Excel",
                "description": "Clique em Exportar Tabela para baixar a tabela dinâmica atual como um arquivo Excel com os detalhes da sua empresa e um registro de data e hora de geração. Use isso para compartilhar resumos de desempenho com a liderança ou para documentação de ciclos de avaliação.",
            },
        },
    },
    "multiple-approval-condition-tour": {
        "title": "Condição de Aprovação Múltipla",
        "description": "Um tour guiado pela página de Condição de Aprovação Múltipla — criando regras de aprovação em múltiplos níveis, definindo critérios e revisando cadeias de aprovação.",
        "steps": {
            1: {
                "title": "Condição de Aprovação Múltipla",
                "description": "A página de Condição de Aprovação Múltipla permite definir regras que exigem mais de um aprovador para solicitações específicas — como licença, horas extras ou despesas — com base em critérios como departamento, tipo de funcionário ou valor. Depois de configurada, as solicitações que atendem a uma condição são automaticamente encaminhadas pela cadeia de aprovação em múltiplos níveis.",
            },
            2: {
                "title": "Lista de Condições",
                "description": "Cada linha mostra uma condição de aprovação — o nome da condição, o módulo ao qual se aplica (Licença, Presença etc.), os critérios que a acionam e o número de níveis de aprovação exigidos. Clique em qualquer linha para ver o detalhe completo da condição, incluindo a lista ordenada de aprovadores.",
            },
            3: {
                "title": "Criar Condição",
                "description": "Clique em Criar para definir uma nova condição de aprovação múltipla. Selecione o módulo, defina os critérios (como departamento ou tipo de funcionário), depois adicione os aprovadores ordenados para cada nível. As solicitações que atendem à condição vão exigir a aprovação de cada aprovador em sequência antes de serem aprovadas.",
            },
            4: {
                "title": "Detalhe da Condição",
                "description": "Clique em qualquer linha de condição para abrir sua visualização de detalhes. Aqui você pode revisar a cadeia de aprovação completa — o aprovador de cada nível, os critérios que acionam a condição e o módulo ao qual ela se aplica. Use esta visualização para verificar se o encaminhamento está configurado corretamente antes de entrar em vigor.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para localizar rapidamente uma condição de aprovação por nome ou módulo. A lista é atualizada conforme você digita, facilitando encontrar uma condição específica quando há muitas configuradas.",
            },
        },
    },
    "multiple-approval-condition-form-tour": {
        "title": "Formulário de Condição de Aprovação",
        "description": "Um tour guiado pelo formulário de Condição de Aprovação Múltipla — definindo critérios, escolhendo aprovadores e construindo uma cadeia de aprovação em múltiplos níveis.",
        "steps": {
            1: {
                "title": "Formulário de Condição de Aprovação Múltipla",
                "description": "Este formulário permite definir uma regra que encaminha solicitações específicas por múltiplos aprovadores em sequência. Preencha os critérios da condição para especificar quais solicitações são afetadas, depois escolha os administradores que devem aprová-las em ordem.",
            },
            2: {
                "title": "Departamento",
                "description": "Selecione o departamento ao qual esta condição de aprovação se aplica. Deixe em branco para aplicar a condição a todos os departamentos. Quando um departamento é selecionado, apenas as solicitações de funcionários daquele departamento serão encaminhadas por esta cadeia de aprovação.",
            },
            3: {
                "title": "Campo da Condição",
                "description": "Escolha o atributo do funcionário a ser avaliado — por exemplo, Cargo, Tipo de Trabalho ou Tipo de Funcionário. A condição vai verificar esse campo no funcionário solicitante para decidir se a cadeia de aprovação em múltiplos níveis se aplica.",
            },
            4: {
                "title": "Operador e Valor da Condição",
                "description": "Defina o operador (igual a, contém etc.) e o valor a ser comparado com o Campo da Condição. Por exemplo, Campo da Condição = Cargo, Operador = igual a, Valor = Administrador. As solicitações de funcionários que atendem a essa regra serão encaminhadas pela cadeia de aprovação.",
            },
            5: {
                "title": "Empresa",
                "description": "Opcionalmente, restrinja esta condição a uma empresa específica. Em configurações com múltiplas empresas, isso garante que a cadeia de aprovação se aplique apenas aos funcionários da empresa selecionada. Deixe em branco para aplicar a condição a toda a empresa.",
            },
            6: {
                "title": "Administradores de Aprovação",
                "description": "Selecione o aprovador de primeiro nível para esta condição. Este administrador receberá a solicitação de aprovação primeiro. Depois que ele aprovar, a solicitação avança para o próximo nível, se houver um configurado.",
            },
            7: {
                "title": "Adicionar Mais Administradores",
                "description": "Clique em 'Adicionar mais administradores' para adicionar níveis de aprovação extras. Cada nível adiciona outro administrador que deve aprovar a solicitação em sequência — a solicitação só é concluída quando todos os níveis a aprovarem. Use isso para construir uma hierarquia completa em múltiplos níveis.",
            },
            8: {
                "title": "Aplicar",
                "description": "Clique em Aplicar para salvar a condição. A partir deste ponto, qualquer solicitação que atenda aos critérios que você definiu será automaticamente encaminhada pela cadeia de aprovação configurada — na ordem em que os administradores foram adicionados.",
            },
        },
    },
    "mail-templates-tour": {
        "title": "Modelos de E-mail",
        "description": "Um tour guiado pela página de Modelos de E-mail — criando modelos de e-mail reutilizáveis com marcadores dinâmicos, editando os existentes e gerenciando duplicatas.",
        "steps": {
            1: {
                "title": "Modelos de E-mail",
                "description": "A página de Modelos de E-mail permite criar e gerenciar modelos de e-mail reutilizáveis usados em todo o sistema — para aprovações de licença, mensagens de integração, notificações de folha de pagamento e mais. Os modelos suportam marcadores dinâmicos, de forma que cada e-mail seja personalizado com os dados do destinatário.",
            },
            2: {
                "title": "Galeria de Modelos",
                "description": "Cada cartão na galeria representa um modelo de e-mail. O cartão mostra o nome do modelo e uma pré-visualização do conteúdo do corpo. Percorra a galeria para navegar por todos os modelos disponíveis em um só olhar.",
            },
            3: {
                "title": "Criar Modelo",
                "description": "Clique em Criar para adicionar um novo modelo de e-mail. Dê a ele um título, escreva o corpo usando o editor de texto formatado, e insira marcadores dinâmicos digitando '{' para autocompletar com campos do remetente ou destinatário, como nome, departamento ou datas de licença.",
            },
            4: {
                "title": "Cartão do Modelo",
                "description": "Cada cartão exibe o nome do modelo e uma pré-visualização rolável do corpo. A pré-visualização dá uma verificação visual rápida do layout e do conteúdo antes de você abri-lo para edição.",
            },
            5: {
                "title": "Visualizar e Editar Modelo",
                "description": "Clique em 'Ver Modelo' em qualquer cartão para abrir o modelo em um editor modal. Você pode atualizar o título, reescrever o corpo, ajustar o escopo de empresa e salvar suas alterações. O editor de texto formatado suporta formatação e o atalho '{' para inserir marcadores de dados.",
            },
            6: {
                "title": "Duplicar e Excluir",
                "description": "Use os ícones no canto superior direito de cada cartão para duplicar ou excluir um modelo. Duplicar copia o modelo para que você possa personalizar uma variante sem começar do zero. Excluir remove o modelo permanentemente — confirme o aviso antes de continuar.",
            },
        },
    },
    "automations-tour": {
        "title": "Automações",
        "description": "Um tour guiado pela página de Automações — criando regras de e-mail e notificação orientadas por eventos, carregando modelos pré-configurados e gerenciando sua biblioteca de automações.",
        "steps": {
            1: {
                "title": "Automações",
                "description": "A página de Automações permite configurar e-mails e notificações no aplicativo automatizados que são disparados quando eventos específicos ocorrem — como uma solicitação de licença sendo aprovada, um novo funcionário sendo integrado, ou um registro de presença sendo criado. Depois de configuradas, as automações funcionam silenciosamente em segundo plano, sem nenhuma ação manual.",
            },
            2: {
                "title": "Lista de Automações",
                "description": "Cada linha mostra uma automação configurada — seu título, o modelo que ela observa, o evento gatilho, o canal de entrega (E-mail, Notificação ou ambos) e o mapeamento de e-mail (para quem a mensagem é enviada). Clique em qualquer linha para abrir a visualização completa de detalhes.",
            },
            3: {
                "title": "Criar Automação",
                "description": "Clique em Criar para definir uma nova automação. Escolha o modelo a observar (por exemplo, Solicitação de Licença), selecione o evento gatilho (criado, atualizado etc.), escreva o assunto e o corpo do e-mail usando marcadores dinâmicos, e escolha se o envio será por e-mail, notificação no aplicativo ou ambos.",
            },
            4: {
                "title": "Detalhe da Automação",
                "description": "Clique em qualquer linha de automação para abrir sua visualização de detalhes. O painel de detalhes mostra a configuração completa — gatilho, condições, destinatários e corpo da mensagem. Use o botão Editar para modificar a automação ou o botão Excluir para removê-la permanentemente.",
            },
            5: {
                "title": "Ações",
                "description": "O menu Ações oferece dois utilitários: 'Carregar Automações' permite importar modelos de automação pré-configurados diretamente para sua configuração; 'Atualizar Automações' reconecta os manipuladores de sinal da automação — use isso se as automações pararem de disparar após uma reinicialização do servidor ou uma alteração de configuração.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar automações por título ou nome do modelo. A lista é atualizada conforme você digita, facilitando localizar uma automação específica quando há muitas configuradas.",
            },
        },
    },
    "holidays-tour": {
        "title": "Feriados",
        "description": "Um tour guiado pela página de Feriados — criando e gerenciando o calendário de feriados da empresa, importando ou exportando dados de feriados, e usando pesquisa e filtro para encontrar feriados específicos.",
        "steps": {
            1: {
                "title": "Feriados",
                "description": "A página de Feriados permite gerenciar o calendário oficial de feriados da empresa. Defina feriados únicos ou recorrentes com datas de início e término, e o sistema vai bloquear automaticamente as deduções de licença e as expectativas de presença nesses dias para todos os funcionários.",
            },
            2: {
                "title": "Lista de Feriados",
                "description": "A tabela lista todos os feriados configurados com seu nome, data de início, data de término e se são recorrentes anualmente. Clique em qualquer cabeçalho de coluna para ordenar a lista. Use as caixas de seleção para selecionar feriados individuais ou selecionar todos para ações em massa.",
            },
            3: {
                "title": "Criar Feriado",
                "description": "Clique em Criar para adicionar um novo feriado. Informe o nome do feriado, defina as datas de início e término, escolha se ele se repete todo ano e, opcionalmente, restrinja-o a empresas específicas. Depois de salvo, o feriado aparece em todos os cálculos de licença e presença dos funcionários.",
            },
            4: {
                "title": "Detalhe do Feriado",
                "description": "Clique em qualquer linha de feriado para abrir sua visualização de detalhes. O painel de detalhes mostra o registro completo — nome, datas de início e término, status de recorrência e empresa. Use o botão Editar dentro do painel para atualizar o feriado ou o botão Excluir para removê-lo.",
            },
            5: {
                "title": "Ações",
                "description": "O menu Ações oferece operações em massa — Importar para enviar uma planilha de feriados, Exportar para baixar a lista, e Excluir para remover todos os feriados selecionados de uma vez. Marque as caixas de seleção na lista antes de usar uma ação em massa.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar feriados instantaneamente por nome. A lista é atualizada conforme você digita — útil quando você tem um grande número de feriados configurados em várias empresas ou regiões.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por nome do feriado, intervalo de datas, empresa ou se o feriado é recorrente. Aplique vários critérios juntos para focar em um subconjunto específico — por exemplo, todos os feriados recorrentes de uma determinada empresa.",
            },
        },
    },
    "company-leaves-tour": {
        "title": "Licenças da Empresa",
        "description": "Um tour guiado pela página de Licenças da Empresa — definindo dias de descanso semanais, revisando registros configurados e gerenciando regras de dias de descanso específicas da empresa.",
        "steps": {
            1: {
                "title": "Licenças da Empresa",
                "description": "A página de Licenças da Empresa permite definir quais dias da semana são tratados como dias de descanso obrigatórios para a empresa — por exemplo, toda sexta-feira ou todo domingo. Esses dias de descanso semanais são considerados automaticamente nos cálculos de saldo de licença e no acompanhamento de presença.",
            },
            2: {
                "title": "Lista de Licenças da Empresa",
                "description": "Cada linha mostra uma licença da empresa configurada — a semana em que ela ocorre e o dia específico da semana. Clique em qualquer linha para abrir seu painel de detalhes, onde você pode revisar o registro completo ou fazer edições.",
            },
            3: {
                "title": "Criar Licença da Empresa",
                "description": "Clique em Criar para adicionar um novo dia de descanso semanal. Selecione o número da semana (primeira, segunda, última etc.) e o dia da semana (segunda a domingo). Opcionalmente, restrinja a licença a uma empresa específica em configurações com múltiplas empresas.",
            },
            4: {
                "title": "Detalhe da Licença da Empresa",
                "description": "Clique em qualquer linha para abrir a visualização de detalhes daquela licença da empresa. O painel mostra qual semana e dia estão configurados, junto com a empresa à qual se aplica. Use o botão Editar para atualizar o registro ou o botão Excluir para removê-lo.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar licenças da empresa por semana ou dia. A lista é atualizada conforme você digita — útil quando você tem várias empresas, cada uma com configurações diferentes de dias de descanso semanais.",
            },
            6: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por semana, dia da semana ou empresa. Use isso para revisar rapidamente as regras de dia de descanso de uma empresa específica ou para verificar se um determinado dia já está configurado.",
            },
        },
    },
    "restricted-days-tour": {
        "title": "Dias Restritos",
        "description": "Um tour guiado pela página de Dias Restritos — definindo períodos de bloqueio de licença para equipes específicas, revisando restrições existentes e gerenciando-as em massa.",
        "steps": {
            1: {
                "title": "Dias Restritos",
                "description": "A página de Dias Restritos permite bloquear intervalos de datas específicos durante os quais os funcionários não podem enviar solicitações de licença. Use isso para impor períodos de bloqueio — como temporadas de pico de negócios, períodos de auditoria ou prazos críticos de projeto — para departamentos ou cargos específicos.",
            },
            2: {
                "title": "Lista de Dias Restritos",
                "description": "Cada linha mostra um período restrito — seu título, datas de início e término, o departamento e o cargo aos quais se aplica, e uma breve descrição. Clique em qualquer linha para abrir seu painel completo de detalhes.",
            },
            3: {
                "title": "Criar Dia Restrito",
                "description": "Clique em Criar para definir um novo período restrito. Defina um título, o intervalo de datas, opcionalmente restrinja-o a um departamento ou cargo específico, e adicione uma descrição explicando por que a licença é restrita naquele período.",
            },
            4: {
                "title": "Detalhe do Dia Restrito",
                "description": "Clique em qualquer linha para abrir a visualização de detalhes daquela restrição. O painel mostra o intervalo de datas completo, o escopo e a descrição. Use o botão Editar para modificar a restrição ou o botão Excluir para removê-la por completo.",
            },
            5: {
                "title": "Ações",
                "description": "O menu Ações oferece uma opção de Excluir em massa. Selecione os dias restritos que você quer remover usando as caixas de seleção na lista, depois escolha Excluir no menu Ações para removê-los todos de uma vez.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar dias restritos por título, departamento ou cargo. A lista é atualizada conforme você digita, facilitando verificar se um determinado período ou equipe já tem uma restrição configurada.",
            },
            7: {
                "title": "Filtrar",
                "description": "Clique em Filtrar para restringir a lista por intervalo de datas, departamento, cargo ou empresa. Use isso para revisar todas as restrições que afetam uma equipe específica ou para identificar períodos de bloqueio sobrepostos.",
            },
        },
    },
    "individual-payslip-tour": {
        "title": "Holerite Individual",
        "description": "Um tour guiado pela visualização de holerite individual — revisando o detalhamento do pagamento, atualizando o status, baixando e enviando holerites por e-mail.",
        "steps": {
            1: {
                "title": "Holerite Individual",
                "description": "Esta página mostra o holerite completo de um único funcionário e período de pagamento. Você pode revisar o detalhamento completo do pagamento — salário básico, auxílios, deduções e salário líquido — e realizar ações como alterar o status, baixar ou enviar o holerite por e-mail.",
            },
            2: {
                "title": "Status do Holerite",
                "description": "Use esta lista suspensa para atualizar o status do holerite — Rascunho, Revisão em Andamento, Confirmado ou Pago. Alterar para Confirmado bloqueia os valores; marcar como Pago registra que o salário foi desembolsado.",
            },
            3: {
                "title": "Baixar Holerite",
                "description": "Clique no ícone de download para salvar este holerite como um PDF. Útil para compartilhar com o funcionário, armazenar registros ou anexar a relatórios financeiros.",
            },
            4: {
                "title": "Enviar por E-mail",
                "description": "Clique no ícone de e-mail para enviar este holerite diretamente ao funcionário. Depois de enviado, o ícone fica verde para confirmar a entrega. Os funcionários podem então ver o holerite pelo próprio portal de autoatendimento.",
            },
            5: {
                "title": "Detalhes do Funcionário e Salário Líquido",
                "description": "O bloco de resumo mostra o nome do funcionário, ID, departamento e conta bancária junto com o salário líquido, o salário básico real, os dias pagos e quaisquer dias de perda de remuneração. Isso dá uma visão rápida antes de revisar o detalhamento completo abaixo.",
            },
            6: {
                "title": "Detalhamento do Pagamento",
                "description": "O corpo principal lista cada ganho e dedução linha por linha — salário básico, auxílios, deduções e o salário líquido final. Revise cada componente aqui para verificar se o holerite está correto antes de confirmá-lo ou enviá-lo ao funcionário.",
            },
        },
    },
    "filing-status-tour": {
        "title": "Status de Arquivamento",
        "description": "Um tour guiado pela página de Status de Arquivamento — criando e gerenciando categorias de declaração de impostos e suas faixas de imposto associadas para a folha de pagamento.",
        "steps": {
            1: {
                "title": "Status de Arquivamento",
                "description": "A página de Status de Arquivamento permite definir as categorias de declaração de impostos usadas na folha de pagamento — como Solteiro, Casado com Declaração Conjunta ou Chefe de Família. Cada status de arquivamento agrupa um conjunto de faixas de imposto que determinam como a renda do funcionário é tributada.",
            },
            2: {
                "title": "Lista de Status de Arquivamento",
                "description": "Cada linha representa um status de arquivamento. Clique em uma linha para expandi-la e ver as faixas de imposto associadas a esse status — as faixas de renda e as alíquotas correspondentes aplicadas durante o cálculo da folha de pagamento.",
            },
            3: {
                "title": "Linha de Status de Arquivamento",
                "description": "Clique em qualquer linha de status de arquivamento para expandi-la e ver suas faixas de imposto. As faixas definem os intervalos de renda e o percentual de imposto aplicado em cada faixa para os funcionários atribuídos a esse status de arquivamento.",
            },
            4: {
                "title": "Ações",
                "description": "Cada linha de status de arquivamento tem um botão Ações. Use-o para criar uma nova faixa de imposto sob aquele status, atualizar o nome do status de arquivamento, ou excluí-lo. As alterações aqui afetam diretamente os cálculos de imposto da folha de pagamento.",
            },
            5: {
                "title": "Criar um Status de Arquivamento",
                "description": "Clique em Criar para adicionar um novo status de arquivamento. Dê a ele um nome e depois use seu menu Ações para adicionar as faixas de imposto que se aplicam. Os status de arquivamento são vinculados aos contratos dos funcionários para determinar o tratamento fiscal correto durante a folha de pagamento.",
            },
            6: {
                "title": "Pesquisar",
                "description": "Digite na caixa de pesquisa para filtrar status de arquivamento por nome. Útil quando você tem vários status configurados e precisa localizar um específico rapidamente.",
            },
        },
    },
    "objective-detailed-view-tour": {
        "title": "Visualização Detalhada do Objetivo",
        "description": "Um tour guiado pela Visualização Detalhada do Objetivo — revisando os detalhes do objetivo, gerenciando responsáveis, acompanhando resultados-chave e monitorando o progresso.",
        "steps": {
            1: {
                "title": "Visualização Detalhada do Objetivo",
                "description": "Esta página mostra tudo sobre um único objetivo de OKR — seus detalhes, os funcionários atribuídos a ele, seus resultados-chave, progresso e status. Os administradores podem editar o objetivo, adicionar responsáveis, acompanhar o progresso e registrar atividades, tudo a partir daqui.",
            },
            2: {
                "title": "Detalhes do Objetivo",
                "description": "O cartão de cabeçalho mostra o título do objetivo junto com seus administradores, duração e descrição. Isso dá uma visão rápida do que o objetivo pretende alcançar e de quem é responsável por ele.",
            },
            3: {
                "title": "Editar Objetivo",
                "description": "Clique no botão Editar para atualizar o título, a descrição, a duração ou os administradores do objetivo. As alterações aqui se aplicam a todos os funcionários atribuídos a este objetivo.",
            },
            4: {
                "title": "Adicionar Responsáveis",
                "description": "Clique no botão Adicionar Responsáveis para atribuir funcionários adicionais a este objetivo. Cada funcionário atribuído terá seu próprio conjunto de resultados-chave e progresso acompanhado de forma independente sob este objetivo.",
            },
            5: {
                "title": "Objetivos dos Funcionários",
                "description": "Cada linha abaixo representa um funcionário atribuído a este objetivo. Você pode ver seu nome, a barra de progresso, o status atual e os botões de ação. Clique em uma linha para expandi-la e ver ou gerenciar os resultados-chave do funcionário.",
            },
            6: {
                "title": "Linha do Funcionário",
                "description": "Clique em qualquer linha de funcionário para expandi-la e ver todos os resultados-chave atribuídos a esse funcionário para este objetivo. A barra de progresso mostra o quanto ele avançou na conclusão do objetivo.",
            },
            7: {
                "title": "Status do Objetivo",
                "description": "Cada linha de funcionário tem uma lista suspensa de status — Não Iniciado, Em Andamento, Concluído ou Cancelado. Atualize-a para refletir o estado atual do progresso do funcionário neste objetivo.",
            },
            8: {
                "title": "Registro de Atividades",
                "description": "Clique no ícone de atividade em uma linha de funcionário para abrir a barra lateral de atividades. Ela mostra uma linha do tempo de todas as atualizações — mudanças de status, edições de resultado-chave, comentários e atualizações de progresso — para o objetivo desse funcionário.",
            },
            9: {
                "title": "Adicionar Resultado-Chave",
                "description": "Clique no botão Adicionar Resultado-Chave em uma linha de funcionário para definir um resultado mensurável para esse funcionário sob este objetivo. Defina o título do resultado-chave, o valor-alvo, a unidade e a data final para acompanhar o progresso dele em direção à meta.",
            },
        },
    },
    "faq-view-tour": {
        "title": "Visualização de Perguntas Frequentes",
        "description": "Um tour guiado pela página de Visualização de Perguntas Frequentes — navegando por perguntas e respostas, criando novas Perguntas Frequentes e filtrando por marcador dentro de uma categoria.",
        "steps": {
            1: {
                "title": "Visualização de Perguntas Frequentes",
                "description": "Esta página mostra todas as Perguntas Frequentes dentro desta categoria. Os funcionários podem navegar e expandir as perguntas para ler as respostas. Os administradores podem adicionar novas Perguntas Frequentes, filtrar por marcadores e excluir ou editar entradas existentes.",
            },
            2: {
                "title": "Lista de Perguntas Frequentes",
                "description": "Cada linha é uma Pergunta Frequente. Clique em uma linha para expandi-la e ler a resposta completa. A pergunta é exibida no cabeçalho e a resposta aparece abaixo, junto com quaisquer marcadores que a categorizem ainda mais.",
            },
            3: {
                "title": "Criar Pergunta Frequente",
                "description": "Clique em Criar para adicionar uma nova pergunta e resposta a esta categoria. Escreva a pergunta, adicione uma resposta em texto formatado e, opcionalmente, atribua marcadores para facilitar a filtragem. As Perguntas Frequentes publicadas ficam imediatamente visíveis para todos os funcionários.",
            },
            4: {
                "title": "Filtrar por Marcador",
                "description": "Clique em Filtrar para restringir a lista de Perguntas Frequentes por marcador. Os marcadores ajudam a organizar as Perguntas Frequentes dentro de uma categoria — por exemplo, por área de política ou tópico. Selecione um ou mais marcadores e aplique o filtro para mostrar apenas as perguntas correspondentes.",
            },
            5: {
                "title": "Pesquisar",
                "description": "Use a barra de pesquisa para encontrar Perguntas Frequentes por palavra-chave. Conforme você digita, a lista é atualizada para mostrar as perguntas correspondentes desta categoria. Esta é a forma mais rápida de localizar uma resposta específica sem precisar rolar por todas as entradas.",
            },
        },
    },
}


def backfill(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    TourStep = apps.get_model("horilla_tour", "TourStep")
    TourTranslation = apps.get_model("horilla_tour", "TourTranslation")
    TourStepTranslation = apps.get_model("horilla_tour", "TourStepTranslation")

    for tour in Tour.objects.all():
        translation = TRANSLATIONS.get(tour.slug)
        if translation is None:
            continue
        TourTranslation.objects.update_or_create(
            tour=tour,
            language="pt-br",
            defaults={
                "title": translation["title"],
                "description": translation["description"],
            },
        )
        steps_translation = translation.get("steps", {})
        for tour_step in tour.steps.all():
            step_translation = steps_translation.get(tour_step.sequence)
            if step_translation is None:
                continue
            TourStepTranslation.objects.update_or_create(
                tour_step=tour_step,
                language="pt-br",
                defaults={
                    "title": step_translation["title"],
                    "description": step_translation["description"],
                },
            )


def unbackfill(apps, schema_editor):
    TourTranslation = apps.get_model("horilla_tour", "TourTranslation")
    TourStepTranslation = apps.get_model("horilla_tour", "TourStepTranslation")
    TourTranslation.objects.filter(language="pt-br").delete()
    TourStepTranslation.objects.filter(language="pt-br").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("horilla_tour", "0089_backfill_english_tour_translations"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
