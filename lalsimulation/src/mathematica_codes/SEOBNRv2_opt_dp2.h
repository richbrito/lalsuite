REAL8 tmp1=1.*e3z;
REAL8 tmp3=0.+tmp1;
REAL8 tmp4=1.*tmp3;
REAL8 tmp5=0.+tmp4;
REAL8 tmp9=x->data[0]*x->data[0];
REAL8 tmp12=coeffs->KK*eta;
REAL8 tmp13=-1.+tmp12;
REAL8 tmp17=(1.0/(x->data[0]*x->data[0]));
REAL8 tmp10=0.+tmp9;
REAL8 tmp11=1/tmp10;
REAL8 tmp20=1/x->data[0];
REAL8 tmp16=sigmaKerr->data[2]*sigmaKerr->data[2];
REAL8 tmp14=(1.0/(tmp13*tmp13));
REAL8 tmp15=1.*tmp14;
REAL8 tmp18=1.*tmp16*tmp17;
REAL8 tmp19=1/tmp13;
REAL8 tmp21=2.*tmp19*tmp20;
REAL8 tmp22=tmp15+tmp18+tmp21;
REAL8 tmp24=coeffs->k0*eta;
REAL8 tmp25=1./(x->data[0]*x->data[0]*x->data[0]*x->data[0]);
REAL8 tmp26=1.*coeffs->k4*tmp25;
REAL8 tmp27=1./(x->data[0]*x->data[0]*x->data[0]);
REAL8 tmp28=1.*coeffs->k3*tmp27;
REAL8 tmp29=1.*coeffs->k2*tmp17;
REAL8 tmp30=1.*coeffs->k1*tmp20;
REAL8 tmp31=pow(x->data[0],-5.);
REAL8 tmp32=1.*tmp20;
REAL8 tmp33=log(tmp32);
REAL8 tmp34=coeffs->k5l*tmp33;
REAL8 tmp35=coeffs->k5+tmp34;
REAL8 tmp36=1.*tmp31*tmp35;
REAL8 tmp37=1.+tmp26+tmp28+tmp29+tmp30+tmp36;
REAL8 tmp38=log(tmp37);
REAL8 tmp39=eta*tmp38;
REAL8 tmp40=1.+tmp24+tmp39;
REAL8 tmp6=0.+p->data[2];
REAL8 tmp7=tmp5*tmp6;
REAL8 tmp8=0.+tmp7;
REAL8 tmp48=-3.*eta;
REAL8 tmp42=tmp16+tmp9;
REAL8 tmp43=tmp42*tmp42;
REAL8 tmp44=-(tmp16*tmp22*tmp40*tmp9);
REAL8 tmp45=tmp43+tmp44;
REAL8 tmp76=sqrt(tmp16);
REAL8 tmp71=1/tmp45;
REAL8 tmp80=(x->data[0]*x->data[0]*x->data[0]);
REAL8 tmp86=eta*eta;
REAL8 tmp56=0.+p->data[0];
REAL8 tmp57=1.*tmp56;
REAL8 tmp58=0.+tmp57;
REAL8 tmp59=tmp58*tmp58;
REAL8 tmp60=26.+tmp48;
REAL8 tmp61=2.*eta*tmp27*tmp60;
REAL8 tmp62=6.*eta*tmp17;
REAL8 tmp63=1.+tmp61+tmp62;
REAL8 tmp64=log(tmp63);
REAL8 tmp65=1.+tmp64;
REAL8 tmp54=tmp8*tmp8;
REAL8 tmp55=1.*tmp11*tmp54*tmp9;
REAL8 tmp66=1.*tmp11*tmp22*tmp40*tmp59*tmp65*tmp9;
REAL8 tmp67=0.+p->data[1];
REAL8 tmp68=tmp3*tmp67;
REAL8 tmp69=0.+tmp68;
REAL8 tmp70=tmp69*tmp69;
REAL8 tmp72=1.*tmp10*tmp70*tmp71*tmp9;
REAL8 tmp93=pow(x->data[0],6.);
REAL8 tmp94=(1.0/(tmp10*tmp10));
REAL8 tmp96=(x->data[0]*x->data[0]*x->data[0]*x->data[0]);
REAL8 tmp97=0.+tmp55+tmp66+tmp72;
REAL8 tmp116=sqrt(tmp10);
REAL8 tmp81=6.*sigmaKerr->data[2]*tmp11*tmp5*tmp8*tmp80;
REAL8 tmp82=8.*sigmaStar->data[2]*tmp11*tmp5*tmp8*tmp80;
REAL8 tmp83=tmp81+tmp82;
REAL8 tmp84=0.08333333333333333*eta*tmp20*tmp83;
REAL8 tmp85=-109.*eta;
REAL8 tmp87=51.*tmp86;
REAL8 tmp88=tmp85+tmp87;
REAL8 tmp89=8.*tmp11*tmp5*tmp8*tmp80*tmp88;
REAL8 tmp90=-6.*eta;
REAL8 tmp91=39.*tmp86;
REAL8 tmp92=tmp90+tmp91;
REAL8 tmp95=-12.*tmp22*tmp40*tmp5*tmp59*tmp65*tmp8*tmp92*tmp93*tmp94;
REAL8 tmp98=-180.*eta*tmp11*tmp5*tmp8*tmp96*tmp97;
REAL8 tmp99=tmp89+tmp95+tmp98;
REAL8 tmp100=0.006944444444444444*sigmaKerr->data[2]*tmp17*tmp99;
REAL8 tmp101=103.*eta;
REAL8 tmp102=-60.*tmp86;
REAL8 tmp103=tmp101+tmp102;
REAL8 tmp104=-4.*tmp103*tmp11*tmp5*tmp8*tmp80;
REAL8 tmp105=-16.*eta;
REAL8 tmp106=21.*tmp86;
REAL8 tmp107=tmp105+tmp106;
REAL8 tmp108=-12.*tmp107*tmp22*tmp40*tmp5*tmp59*tmp65*tmp8*tmp93*tmp94;
REAL8 tmp109=3.*eta;
REAL8 tmp110=23.+tmp109;
REAL8 tmp111=-4.*eta*tmp11*tmp110*tmp5*tmp8*tmp96*tmp97;
REAL8 tmp112=tmp104+tmp108+tmp111;
REAL8 tmp113=0.013888888888888888*sigmaStar->data[2]*tmp112*tmp17;
REAL8 tmp114=tmp100+tmp113+tmp84;
REAL8 tmp139=(tmp58*tmp58*tmp58*tmp58);
REAL8 tmp140=tmp22*tmp22;
REAL8 tmp141=tmp65*tmp65;
REAL8 tmp142=tmp40*tmp40;
REAL8 tmp145=tmp97*tmp97;
REAL8 tmp117=tmp22*tmp40*tmp9;
REAL8 tmp118=sqrt(tmp117);
REAL8 tmp119=-tmp118;
REAL8 tmp120=tmp10*tmp22*tmp40*tmp71*tmp9;
REAL8 tmp121=sqrt(tmp120);
REAL8 tmp122=1.*tmp116*tmp121;
REAL8 tmp123=tmp119+tmp122;
REAL8 tmp124=1.+tmp55+tmp66+tmp72;
REAL8 tmp127=1.*coeffs->d1v2*eta*sigmaKerr->data[2]*tmp27;
REAL8 tmp128=-8.*sigmaKerr->data[2];
REAL8 tmp129=14.*sigmaStar->data[2];
REAL8 tmp130=-36.*sigmaKerr->data[2]*tmp11*tmp22*tmp40*tmp59*tmp65*tmp80;
REAL8 tmp131=-30.*sigmaStar->data[2]*tmp11*tmp22*tmp40*tmp59*tmp65*tmp80;
REAL8 tmp132=3.*sigmaKerr->data[2]*tmp97*x->data[0];
REAL8 tmp133=4.*sigmaStar->data[2]*tmp97*x->data[0];
REAL8 tmp134=tmp128+tmp129+tmp130+tmp131+tmp132+tmp133;
REAL8 tmp135=0.08333333333333333*eta*tmp134*tmp20;
REAL8 tmp136=27.*eta;
REAL8 tmp137=-353.+tmp136;
REAL8 tmp138=-2.*eta*tmp137;
REAL8 tmp143=360.*tmp139*tmp140*tmp141*tmp142*tmp86*tmp93*tmp94;
REAL8 tmp144=-2.*tmp103*tmp97*x->data[0];
REAL8 tmp146=-(eta*tmp110*tmp145*tmp9);
REAL8 tmp147=-47.*eta;
REAL8 tmp148=54.*tmp86;
REAL8 tmp149=tmp107*tmp97*x->data[0];
REAL8 tmp150=tmp147+tmp148+tmp149;
REAL8 tmp151=-6.*tmp11*tmp150*tmp22*tmp40*tmp59*tmp65*tmp80;
REAL8 tmp152=tmp138+tmp143+tmp144+tmp146+tmp151;
REAL8 tmp153=0.013888888888888888*sigmaStar->data[2]*tmp152*tmp17;
REAL8 tmp154=8.+tmp109;
REAL8 tmp155=-112.*eta*tmp154;
REAL8 tmp156=810.*tmp139*tmp140*tmp141*tmp142*tmp86*tmp93*tmp94;
REAL8 tmp157=4.*tmp88*tmp97*x->data[0];
REAL8 tmp158=-45.*eta*tmp145*tmp9;
REAL8 tmp159=16.*eta;
REAL8 tmp160=147.*tmp86;
REAL8 tmp161=tmp92*tmp97*x->data[0];
REAL8 tmp162=tmp159+tmp160+tmp161;
REAL8 tmp163=-6.*tmp11*tmp162*tmp22*tmp40*tmp59*tmp65*tmp80;
REAL8 tmp164=tmp155+tmp156+tmp157+tmp158+tmp163;
REAL8 tmp165=0.006944444444444444*sigmaKerr->data[2]*tmp164*tmp17;
REAL8 tmp166=0.+sigmaStar->data[2]+tmp127+tmp135+tmp153+tmp165;
REAL8 tmp23=1/tmp22;
REAL8 tmp41=1/tmp40;
REAL8 tmp173=tmp22*tmp40*tmp65*tmp9;
REAL8 tmp174=sqrt(tmp173);
REAL8 tmp175=sqrt(tmp124);
REAL8 tmp168=1./sqrt(tmp10);
REAL8 tmp178=tmp140*tmp142*tmp65*tmp96;
REAL8 tmp179=1./sqrt(tmp178);
REAL8 tmp180=-2.*tmp22*tmp40*tmp9;
REAL8 tmp181=1/tmp37;
REAL8 tmp182=2.*coeffs->k2;
REAL8 tmp183=3.*coeffs->k3;
REAL8 tmp184=4.*coeffs->k4;
REAL8 tmp185=5.*tmp20*tmp35;
REAL8 tmp186=tmp184+tmp185;
REAL8 tmp187=1.*tmp186*tmp20;
REAL8 tmp188=tmp183+tmp187;
REAL8 tmp189=1.*tmp188*tmp20;
REAL8 tmp190=tmp182+tmp189;
REAL8 tmp191=1.*tmp190*tmp20;
REAL8 tmp192=coeffs->k1+tmp191;
REAL8 tmp193=-(eta*tmp181*tmp192*tmp22);
REAL8 tmp194=1.*tmp19;
REAL8 tmp195=1.*tmp16*tmp20;
REAL8 tmp196=tmp194+tmp195;
REAL8 tmp197=-2.*tmp196*tmp40;
REAL8 tmp198=2.*tmp22*tmp40*x->data[0];
REAL8 tmp199=tmp193+tmp197+tmp198;
REAL8 tmp200=tmp174*tmp199;
REAL8 tmp201=tmp180+tmp200;
REAL8 tmp125=1./sqrt(tmp124);
REAL8 tmp207=1.*tmp11*x->data[0];
REAL8 tmp208=-4.*tmp22*tmp40*tmp80;
REAL8 tmp209=tmp199*tmp42;
REAL8 tmp210=tmp208+tmp209;
REAL8 tmp211=0.5*tmp17*tmp210*tmp23*tmp41*tmp42*tmp71;
REAL8 tmp212=tmp207+tmp211;
REAL8 tmp204=tmp166*tmp5;
REAL8 tmp205=0.+tmp204;
REAL8 tmp77=0.;
REAL8 tmp78=2.*tmp76*x->data[0];
REAL8 tmp79=tmp77+tmp78;
REAL8 tmp202=1.+tmp175;
REAL8 tmp176=1.+tmp175+tmp55+tmp66+tmp72;
REAL8 tmp222=1./sqrt(tmp117);
REAL8 tmp223=1./sqrt(tmp120);
REAL8 tmp224=(1.0/(tmp45*tmp45));
REAL8 tmp225=2.*tmp76;
REAL8 tmp226=0.;
REAL8 tmp227=0.+tmp225+tmp226;
REAL8 tmp228=tmp227*tmp45;
REAL8 tmp229=-4.*tmp42*x->data[0];
REAL8 tmp230=1.*tmp16*tmp199;
REAL8 tmp231=tmp229+tmp230;
REAL8 tmp232=tmp231*tmp79;
REAL8 tmp233=tmp228+tmp232;
REAL8 tmp235=tmp10*tmp10;
REAL8 tmp247=pow(tmp10,-2.5);
REAL8 tmp169=(1.0/sqrt(tmp124*tmp124*tmp124));
REAL8 tmp234=1/tmp202;
REAL8 tmp250=1.*tmp205*tmp22*tmp235*tmp40*tmp70*tmp71*tmp96;
REAL8 tmp251=-(tmp205*tmp22*tmp40*tmp59*tmp65*tmp9);
REAL8 tmp252=tmp10*tmp176*tmp205;
REAL8 tmp253=0.+tmp251+tmp252;
REAL8 tmp254=1.*tmp22*tmp253*tmp40*tmp9;
REAL8 tmp255=0.+tmp250+tmp254;
REAL8 tmp239=2.*tmp11*tmp5*tmp8*tmp9;
REAL8 tmp240=1.*tmp11*tmp125*tmp5*tmp8*tmp9;
REAL8 tmp241=tmp239+tmp240;
REAL8 tmp213=2.*tmp175;
REAL8 tmp214=1.+tmp213;
REAL8 tmp46=tmp11*tmp17*tmp23*tmp41*tmp45;
REAL8 tmp47=1./sqrt(tmp46);
REAL8 tmp49=4.+tmp48;
REAL8 tmp50=1.*p->data[0];
REAL8 tmp51=0.+tmp50;
REAL8 tmp52=(tmp51*tmp51*tmp51*tmp51);
REAL8 tmp53=2.*eta*tmp17*tmp49*tmp52;
REAL8 tmp73=1.+tmp53+tmp55+tmp66+tmp72;
REAL8 tmp170=e3z*tmp166;
REAL8 tmp171=0.+tmp170;
REAL8 tmp221=(1.0/sqrt(tmp10*tmp10*tmp10));
REAL8 tmp177=1/tmp176;
REAL8 tmp259=-0.5*tmp116*tmp121*tmp179*tmp201*tmp202*tmp205*tmp69*x->data[0];
REAL8 tmp260=1.*tmp116*tmp121*tmp205*tmp212*tmp214*tmp69*x->data[0];
REAL8 tmp261=0.+tmp260;
REAL8 tmp262=tmp118*tmp261;
REAL8 tmp263=tmp259+tmp262;
REAL8 tmp264=tmp174*tmp263;
REAL8 tmp265=0.+tmp264;
REAL8 dHdp2=(1.*eta*(-(tmp114*tmp166*tmp27)+1.*e3z*tmp114*tmp71*tmp79-tmp123*tmp168*tmp169*tmp171*tmp5*tmp69*tmp71*tmp8*tmp80-0.5*tmp169*tmp174*tmp222*tmp223*tmp224*tmp233*tmp234*tmp247*tmp255*tmp5*tmp8*tmp9+0.5*tmp125*tmp174*tmp221*tmp222*tmp223*tmp224*tmp233*tmp234*(1.*tmp22*tmp40*tmp9*(tmp10*tmp205*tmp241+tmp10*tmp114*tmp176*tmp5-tmp114*tmp22*tmp40*tmp5*tmp59*tmp65*tmp9)+1.*tmp114*tmp22*tmp235*tmp40*tmp5*tmp70*tmp71*tmp96)+1.*e3z*tmp114*tmp116*tmp123*tmp125*tmp69*tmp71*x->data[0]+1.*tmp11*tmp121*tmp17*tmp174*tmp177*tmp23*tmp41*(-0.5*tmp121*tmp125*tmp168*tmp179*tmp201*tmp205*tmp5*tmp69*tmp8*tmp80-0.5*tmp114*tmp116*tmp121*tmp179*tmp201*tmp202*tmp5*tmp69*x->data[0]+tmp118*(2.*tmp121*tmp125*tmp168*tmp205*tmp212*tmp5*tmp69*tmp8*tmp80+1.*tmp114*tmp116*tmp121*tmp212*tmp214*tmp5*tmp69*x->data[0]))-tmp11*tmp121*tmp17*tmp23*tmp241*tmp265*tmp41*(1.0/(tmp176*tmp176))-(0.5*tmp174*tmp222*tmp223*tmp224*tmp233*tmp247*tmp255*tmp5*tmp8*tmp9*(1.0/(tmp202*tmp202)))/tmp124+(1.*tmp11*tmp47*tmp5*tmp8*tmp9)/sqrt(tmp73)))/sqrt(1.+2.*eta*(-1.+0.5*tmp125*tmp174*tmp221*tmp222*tmp223*tmp224*tmp233*tmp234*tmp255+1.*tmp11*tmp121*tmp17*tmp177*tmp23*tmp265*tmp41+1.*tmp171*tmp71*tmp79+1.*tmp116*tmp123*tmp125*tmp171*tmp69*tmp71*x->data[0]+1.*tmp69*tmp71*tmp79*x->data[0]+1.*coeffs->dheffSSv2*eta*tmp25*(s1Vec->data[2]*s1Vec->data[2]+s2Vec->data[2]*s2Vec->data[2])-0.5*tmp27*(0.+tmp166*tmp166)+tmp47*sqrt(tmp73)));
